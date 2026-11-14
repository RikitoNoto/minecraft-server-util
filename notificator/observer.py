from abc import ABC, abstractmethod
import asyncio
import anyio
from datetime import datetime, time
from log_parser import Log, LogLine
from pathlib import Path


class Handler(ABC):
    @abstractmethod
    async def handle(self, line: LogLine):
        pass

    @abstractmethod
    def is_trigger(self, line: LogLine):
        pass


class Observer:
    def __init__(self):
        pass

    async def observe(
        self, log_path: Path, handlers: list[Handler], interval_ms: int = 1000
    ):

        last_check_line: LogLine | None = None
        async with await anyio.open_file(log_path, mode="r") as file:
            log = Log.model_validate(await file.read())
            if len(log.lines) > 0:
                last_check_line = log.lines[-1]

        while True:
            async with await anyio.open_file(log_path, mode="r") as file:
                log = Log.model_validate(await file.read())

                find_seek_point = False
                for log_line in log.lines:
                    # 前回確認した行までスキップ
                    if log_line == last_check_line:
                        find_seek_point = True
                        continue

                    if not find_seek_point:
                        continue
                    last_check_line = log_line
                    for handler in handlers:
                        if handler.is_trigger(log_line):
                            asyncio.create_task(handler.handle(log_line))
            await asyncio.sleep(interval_ms / 1000)

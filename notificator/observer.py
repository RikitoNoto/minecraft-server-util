from abc import ABC, abstractmethod
import asyncio
import anyio
from datetime import datetime, time
from log_parser import Log, LogLine
import os
from pathlib import Path
from typing import NamedTuple


class Handler(ABC):
    @abstractmethod
    async def handle(self, line: LogLine):
        pass

    @abstractmethod
    def is_trigger(self, line: LogLine):
        pass


class Observer:
    async def __read_log(self, log_path: str) -> Log:
        async with await anyio.open_file(log_path, mode="r") as file:
            return Log.model_validate(await file.read())

    async def __read_initial(self, log_path: str) -> LogLine | None:
        """
        初回読み取り
        チェックポイントとして最後の行を返す
        """
        log = await self.__read_log(log_path)
        if len(log.lines) > 0:
            return log.lines[-1]
        return None

    class SeekPointSearchResult(NamedTuple):
        is_find: bool
        unread_log: Log

    async def __find_seek_point(
        self, log_path: str, last_read_line: LogLine | None
    ) -> SeekPointSearchResult:
        try:
            log = await self.__read_log(log_path)
        except:
            return self.SeekPointSearchResult(True, Log.model_validate(""))

        for i, log_line in enumerate(log.lines):
            # 初回読み取りで空ファイルの場合は、読み取り開始
            if last_read_line is None:
                return self.SeekPointSearchResult(True, log)

            # 前回確認した行がある場合、その行以降をチェックポイントとして返す
            if log_line == last_read_line:
                log.lines = log.lines[i + 1 :]
                return self.SeekPointSearchResult(True, log)

        return self.SeekPointSearchResult(False, log)

    async def observe(
        self, log_dir_path: Path, handlers: list[Handler], interval_ms: int = 1000
    ):
        latest_file = "latest.log"
        log_path = os.path.join(log_dir_path, latest_file)

        last_check_line: LogLine | None = await self.__read_initial(log_path)

        while True:
            is_find, log = await self.__find_seek_point(log_path, last_check_line)

            for line in log.lines:
                last_check_line = line
                for handler in handlers:
                    if handler.is_trigger(line):
                        asyncio.create_task(handler.handle(line))
            await asyncio.sleep(interval_ms / 1000)

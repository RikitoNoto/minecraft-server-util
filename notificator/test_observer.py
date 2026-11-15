import asyncio
from contextlib import suppress
from datetime import date, time, timedelta
from functools import partial
import gzip
import os
from pathlib import Path
import shutil
from tempfile import mkdtemp
from typing import Callable

import pytest

from log_parser import LogLevel, LogLine
from observer import Handler, Observer

# observe のポーリング間隔。テストを速くするため短くする
INTERVAL_MS = 10
# 期待する呼び出しが来るまで待つ上限
TIMEOUT_SEC = 2.0


class HandlerSpy(Handler):
    """handle / is_trigger の呼び出しを記録するだけのスパイ"""

    def __init__(self, is_trigger_result: bool = True) -> None:
        self.handled_lines: list[LogLine] = []
        self.checked_lines: list[LogLine] = []
        self.__is_trigger_result = is_trigger_result

    async def handle(self, line: LogLine) -> None:
        self.handled_lines.append(line)

    def is_trigger(self, line: LogLine) -> bool:
        self.checked_lines.append(line)
        return self.__is_trigger_result

    @property
    def handle_count(self) -> int:
        return len(self.handled_lines)

    @property
    def is_trigger_count(self) -> int:
        return len(self.checked_lines)


class TestHandlerSpy:
    def test_should_record_handle_call(self):
        spy = HandlerSpy()
        line = LogLine.from_line("[20:10:10] [Server thread/INFO]: Stopping server")

        asyncio.run(spy.handle(line))

        assert spy.handle_count == 1
        assert spy.handled_lines == [line]

    @pytest.mark.parametrize("is_trigger_result", [True, False])
    def test_should_record_is_trigger_call_and_return_configured_value(
        self, is_trigger_result: bool
    ):
        spy = HandlerSpy(is_trigger_result=is_trigger_result)
        line = LogLine.from_line("[20:10:10] [Server thread/INFO]: Stopping server")

        assert spy.is_trigger(line) is is_trigger_result
        assert spy.checked_lines == [line]


class TestObserver:
    def __generate_log(self, content: str) -> None:
        self.__tempdir = mkdtemp()
        self.__rotated_count = 0
        self.__create_log(content)

    def __create_log(self, content: str) -> None:
        with open(self.__log_path, mode="w") as file:
            file.write(content)
            file.flush()

    def __append_log(self, content: str) -> None:
        with open(self.__log_path, mode="a") as file:
            file.write(content)
            file.flush()

    def __remove_log(self) -> None:
        os.remove(self.__log_path)

    def __rotate_log(self, content: str = "") -> None:
        """日付が変わったときのログローテーションを再現する

        Minecraft サーバーは日付が変わると、それまでの latest.log を
        「退避日-連番.log.gz」に圧縮して退避し、latest.log を新規作成する
        """
        self.__rotated_count += 1
        rotated_date = date.today() - timedelta(days=1)
        rotated_path = os.path.join(
            self.__tempdir, f"{rotated_date}-{self.__rotated_count}.log.gz"
        )
        with (
            open(self.__log_path, mode="rb") as log_file,
            gzip.open(rotated_path, mode="wb") as rotated_file,
        ):
            shutil.copyfileobj(log_file, rotated_file)
        self.__remove_log()
        self.__create_log(content)

    @property
    def __log_dir(self) -> Path:
        return Path(self.__tempdir)

    @property
    def __log_path(self) -> Path:
        return Path(os.path.join(self.__tempdir, "latest.log"))

    def __observe(
        self,
        handlers: list[Handler],
        appends: list[str],
        until: Callable[[], bool],
        timeout_sec: float = TIMEOUT_SEC,
    ) -> None:
        """observe を裏で動かしつつ appends を追記し、until が真になるまで待つ"""

        self.__observe_with_actions(
            handlers=handlers,
            actions=[partial(self.__append_log, content) for content in appends],
            until=until,
            timeout_sec=timeout_sec,
        )

    def __observe_with_actions(
        self,
        handlers: list[Handler],
        actions: list[Callable[[], None]],
        until: Callable[[], bool],
        timeout_sec: float = TIMEOUT_SEC,
    ) -> None:
        """observe を裏で動かしつつ actions を順に実行し、until が真になるまで待つ"""

        async def run() -> None:
            observer = Observer()
            task = asyncio.create_task(
                observer.observe(self.__log_dir, handlers, interval_ms=INTERVAL_MS)
            )
            try:
                # observe が既存行を読み終えるのを待つ
                await asyncio.sleep(INTERVAL_MS / 1000 * 2)
                for action in actions:
                    action()
                    # observe が変更を読み取るのを待つ
                    await asyncio.sleep(INTERVAL_MS / 1000 * 3)
                await self.__wait_until(until, timeout_sec)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        asyncio.run(run())

    @staticmethod
    async def __wait_until(predicate: Callable[[], bool], timeout_sec: float) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_sec
        while not predicate():
            if loop.time() >= deadline:
                return
            await asyncio.sleep(INTERVAL_MS / 1000)

    def test_should_call_handle_when_log_appended(self):
        self.__generate_log("")
        spy = HandlerSpy()

        self.__observe(
            handlers=[spy],
            appends=["[20:10:10] [Server thread/INFO]: Stopping server\r\n"],
            until=lambda: spy.handle_count >= 1,
        )

        assert spy.handle_count == 1

    def test_should_pass_parsed_log_line_to_handle(self):
        self.__generate_log("")
        spy = HandlerSpy()

        self.__observe(
            handlers=[spy],
            appends=["[20:10:10] [Server thread/INFO]: Stopping server\r\n"],
            until=lambda: spy.handle_count >= 1,
        )

        assert spy.handle_count == 1
        line = spy.handled_lines[0]
        assert line.time == time(20, 10, 10)
        assert line.thread == "Server thread"
        assert line.level == LogLevel.INFO
        assert line.message == "Stopping server"

    def test_should_call_is_trigger_before_handle(self):
        self.__generate_log("")
        spy = HandlerSpy()

        self.__observe(
            handlers=[spy],
            appends=["[20:10:10] [Server thread/INFO]: Stopping server\r\n"],
            until=lambda: spy.handle_count >= 1,
        )

        assert spy.is_trigger_count == 1
        assert spy.checked_lines == spy.handled_lines

    def test_should_not_call_handle_when_is_trigger_returns_false(self):
        self.__generate_log("")
        spy = HandlerSpy(is_trigger_result=False)

        self.__observe(
            handlers=[spy],
            appends=["[20:10:10] [Server thread/INFO]: Stopping server\r\n"],
            until=lambda: spy.is_trigger_count >= 1,
        )

        assert spy.is_trigger_count == 1
        assert spy.handle_count == 0

    def test_should_call_handle_for_each_appended_line(self):
        self.__generate_log("")
        spy = HandlerSpy()

        self.__observe(
            handlers=[spy],
            appends=[
                "[20:10:10] [Server thread/INFO]: Stopping server\r\n",
                "[20:10:11] [Server thread/WARN]: Can't keep up!\r\n",
            ],
            until=lambda: spy.handle_count >= 2,
        )

        assert spy.handle_count == 2
        assert [line.message for line in spy.handled_lines] == [
            "Stopping server",
            "Can't keep up!",
        ]

    def test_should_call_handle_for_each_line_of_a_single_append(self):
        self.__generate_log("")
        spy = HandlerSpy()

        self.__observe(
            handlers=[spy],
            appends=[
                "[20:10:10] [Server thread/INFO]: Stopping server\r\n"
                "[20:10:11] [Server thread/WARN]: Can't keep up!\r\n"
            ],
            until=lambda: spy.handle_count >= 2,
        )

        assert spy.handle_count == 2
        assert [line.message for line in spy.handled_lines] == [
            "Stopping server",
            "Can't keep up!",
        ]

    def test_should_call_all_handlers(self):
        self.__generate_log("")
        triggered = HandlerSpy()
        not_triggered = HandlerSpy(is_trigger_result=False)

        self.__observe(
            handlers=[triggered, not_triggered],
            appends=["[20:10:10] [Server thread/INFO]: Stopping server\r\n"],
            until=lambda: (
                triggered.handle_count >= 1 and not_triggered.is_trigger_count >= 1
            ),
        )

        assert triggered.handle_count == 1
        assert not_triggered.is_trigger_count == 1
        assert not_triggered.handle_count == 0

    def test_should_not_call_handle_for_lines_written_before_observe(self):
        self.__generate_log("[19:00:00] [Server thread/INFO]: Starting server\r\n")
        spy = HandlerSpy()

        self.__observe(
            handlers=[spy],
            appends=["[20:10:10] [Server thread/INFO]: Stopping server\r\n"],
            until=lambda: spy.handle_count >= 1,
        )

        assert [line.message for line in spy.handled_lines] == ["Stopping server"]

    def test_should_not_call_handle_when_nothing_appended(self):
        self.__generate_log("")
        spy = HandlerSpy()

        self.__observe(
            handlers=[spy],
            appends=[],
            until=lambda: False,
            timeout_sec=INTERVAL_MS / 1000 * 10,
        )

        assert spy.handle_count == 0
        assert spy.is_trigger_count == 0

    def test_should_call_handle_for_line_appended_after_log_rotation(self):
        """日付が変わって latest.log が新規作成された後の追記も検知する"""

        self.__generate_log("[23:59:59] [Server thread/INFO]: Saving the game\r\n")
        spy = HandlerSpy()

        self.__observe_with_actions(
            handlers=[spy],
            actions=[
                self.__rotate_log,
                partial(
                    self.__append_log,
                    "[00:00:01] [Server thread/INFO]: Stopping server\r\n",
                ),
            ],
            until=lambda: spy.handle_count >= 1,
        )

        assert [line.message for line in spy.handled_lines] == ["Stopping server"]

    def test_should_call_handle_for_line_written_by_log_rotation(self):
        """ローテーション直後の新ファイルに最初から書かれている行も検知する"""

        self.__generate_log("[23:59:59] [Server thread/INFO]: Saving the game\r\n")
        spy = HandlerSpy()

        self.__observe_with_actions(
            handlers=[spy],
            actions=[
                partial(
                    self.__rotate_log,
                    "[00:00:00] [Server thread/INFO]: Starting minecraft server\r\n",
                )
            ],
            until=lambda: spy.handle_count >= 1,
        )

        assert [line.message for line in spy.handled_lines] == [
            "Starting minecraft server"
        ]

    def test_should_not_call_handle_again_for_lines_rotated_away(self):
        """ローテーション前に検知済みの行を、ローテーション後に再通知しない"""

        self.__generate_log("[19:00:00] [Server thread/INFO]: Starting server\r\n")
        spy = HandlerSpy()

        self.__observe_with_actions(
            handlers=[spy],
            actions=[
                partial(
                    self.__append_log,
                    "[23:59:59] [Server thread/INFO]: Saving the game\r\n",
                ),
                self.__rotate_log,
                partial(
                    self.__append_log,
                    "[00:00:01] [Server thread/INFO]: Stopping server\r\n",
                ),
            ],
            until=lambda: spy.handle_count >= 2,
        )

        assert [line.message for line in spy.handled_lines] == [
            "Saving the game",
            "Stopping server",
        ]

    def test_should_keep_observing_while_log_does_not_exist(self):
        """ローテーション中に latest.log が一時的に存在しなくても監視を継続する"""

        self.__generate_log("[23:59:59] [Server thread/INFO]: Saving the game\r\n")
        spy = HandlerSpy()

        self.__observe_with_actions(
            handlers=[spy],
            actions=[
                self.__remove_log,
                partial(
                    self.__create_log,
                    "[00:00:01] [Server thread/INFO]: Stopping server\r\n",
                ),
            ],
            until=lambda: spy.handle_count >= 1,
        )

        assert [line.message for line in spy.handled_lines] == ["Stopping server"]

    def test_should_call_handle_for_each_line_when_write_same_time(self):
        self.__generate_log("")
        spy = HandlerSpy()

        self.__observe(
            handlers=[spy],
            appends=[
                "[20:10:10] [Server thread/INFO]: Stopping server\r\n"
                "[20:10:10] [Server thread/WARN]: Can't keep up!\r\n"
            ],
            until=lambda: spy.handle_count >= 2,
        )

        assert spy.handle_count == 2
        assert [line.message for line in spy.handled_lines] == [
            "Stopping server",
            "Can't keep up!",
        ]

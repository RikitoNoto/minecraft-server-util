from datetime import time
from log_parser import Log, LogLevel
import pytest


class TestLog:
    def test_should_parse_a_line(self):
        logline = "[20:10:10] [Server thread/INFO]: Stopping server"
        log = Log.model_validate(logline)
        assert len(log.lines) == 1

    def test_should_parse_multi_lines(self):
        loglines = (
            "[20:10:10] [Server thread/INFO]: Stopping server\r\n"
            "[13:30:12] [Server thread/INFO]: Player TEST standing on air - force-sending blocks below\r\n"
        )
        log = Log.model_validate(loglines)
        assert len(log.lines) == 2

    def test_should_parse_log_line_property(self):
        loglines = "[20:10:10] [Server thread/INFO]: Stopping server\r\n"
        log = Log.model_validate(loglines)
        line = log.lines[0]
        assert line.time == time(20, 10, 10)
        assert line.thread == "Server thread"
        assert line.level == LogLevel.INFO
        assert line.message == "Stopping server"

    @pytest.mark.parametrize(
        "level_string, expected",
        [
            ("INFO", LogLevel.INFO),
            ("WARN", LogLevel.WARN),
            ("ERROR", LogLevel.ERROR),
        ],
    )
    def test_should_parse_log_level(self, level_string: str, expected: LogLevel):
        loglines = f"[20:10:10] [Server thread/{level_string}]: Stopping server\r\n"
        log = Log.model_validate(loglines)
        line = log.lines[0]
        assert line.level == expected

from datetime import time
from enum import Enum
from pydantic import BaseModel, model_validator
import re
from typing import Any, Self


class LogLevel(Enum):
    WARN = "WARN"
    INFO = "INFO"
    ERROR = "ERROR"


class LogLine(BaseModel):
    time: time
    thread: str
    level: LogLevel
    message: str

    @classmethod
    def from_line(cls, line: str) -> Self:
        match = re.match(
            "\[(?P<time>.*)\] \[(?P<thread_level>.*)\]: (?P<message>.*)\r?\n?",
            line,
        )
        if not match:
            raise ValueError("invalid format")

        log_time = time.fromisoformat(match.group("time"))
        thread, level_string = match.group("thread_level").split("/")

        return cls(
            time=log_time,
            thread=thread,
            level=LogLevel(level_string),
            message=match.group("message"),
        )


class Log(BaseModel):
    lines: list[LogLine]

    @model_validator(mode="before")
    @classmethod
    def __parse(cls, data: str) -> Any:
        return {
            "lines": [
                LogLine.from_line(line) for line in data.split("\r\n") if line != ""
            ]
        }

from log_parser import LogLevel, LogLine
from pathlib import Path
from observer import Handler, Observer
import re


class UserJoinHandler(Handler):
    def __parse_join_user(self, line: LogLine) -> str | None:
        if line.level == LogLevel.INFO and line.thread == "Server thread":
            match = re.match(
                "^System chat: (?P<user>.*) joined the game$",
                line.message,
            )
            if match:
                return match.group("user")
        return None

    async def handle(self, line: LogLine):
        print(f"user join {self.__parse_join_user(line)}")

    def is_trigger(self, line: LogLine) -> bool:
        return self.__parse_join_user(line) is not None


class UserLeftHandler(Handler):
    def __parse_left_user(self, line: LogLine) -> str | None:
        if line.level == LogLevel.INFO and line.thread == "Server thread":
            match = re.match(
                "^System chat: (?P<user>.*) left the game$",
                line.message,
            )
            if match:
                return match.group("user")
        return None

    async def handle(self, line: LogLine):
        print(f"user left {self.__parse_left_user(line)}")

    def is_trigger(self, line: LogLine) -> bool:
        return self.__parse_left_user(line) is not None


if __name__ == "__main__":
    import asyncio

    observer = Observer()
    asyncio.run(
        observer.observe(
            Path(""),
            handlers=[
                UserJoinHandler(),
                UserLeftHandler(),
            ],
        )
    )

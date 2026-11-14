import aiohttp
from log_parser import LogLevel, LogLine
from pathlib import Path
from observer import Handler, Observer
import re


class UserJoinHandler(Handler):
    def __init__(self, webhook_url: str) -> None:
        self.__webhook_url = webhook_url

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
        async with aiohttp.ClientSession() as session:
            await session.post(
                self.__webhook_url,
                json={
                    "content": f"{self.__parse_join_user(line)}がサーバーに参加しました"
                },
            )

    def is_trigger(self, line: LogLine) -> bool:
        return self.__parse_join_user(line) is not None


class UserLeftHandler(Handler):
    def __init__(self, webhook_url: str) -> None:
        self.__webhook_url = webhook_url

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
        async with aiohttp.ClientSession() as session:
            await session.post(
                self.__webhook_url,
                json={
                    "content": f"{self.__parse_left_user(line)}がサーバーから退出しました"
                },
            )

    def is_trigger(self, line: LogLine) -> bool:
        return self.__parse_left_user(line) is not None


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    from os import getenv

    load_dotenv()

    webhook_url = getenv("WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("WEBHOOK_URLを設定してください")

    logfile_path = getenv("LOGFILE_PATH")
    if not logfile_path:
        raise ValueError("LOGFILE_PATHを設定してください")

    observer = Observer()
    asyncio.run(
        observer.observe(
            Path(logfile_path),
            handlers=[
                UserJoinHandler(webhook_url),
                UserLeftHandler(webhook_url),
            ],
        )
    )

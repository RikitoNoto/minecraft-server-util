from enum import Enum
import os
import re
from datetime import datetime
import time
from collections.abc import Callable
import requests
from dotenv import load_dotenv

load_dotenv()


class LogLevel(Enum):
    WARN = "WARN"
    INFO = "INFO"
    ERROR = "ERROR"


class MinecraftLog:
    line: str
    date: datetime
    thread: str
    level: LogLevel
    domain: str
    content: str

    def __init__(self, line: str) -> None:
        self.line = line
        match = re.match(
            "\[(.*)\] \[(.*)\] \[(.*)\]: (.*)",
            line,
        )
        if not match:
            raise ValueError("invalid format")
        self.date = datetime.strptime(match.group(1), "%d%b%Y %H:%M:%S.%f")
        self.thread = re.match(
            "(.*)\/(.*)",
            match.group(2),
        ).group(1)

        self.level = re.match(
            "(.*)\/(.*)",
            match.group(2),
        ).group(2)
        self.domain = match.group(3)
        self.content = match.group(4)

    def __repr__(self) -> str:
        return self.line


class MinecraftUserLog(MinecraftLog):
    user: str

    def __init__(self, line: str, user_list: list[str]) -> None:
        super().__init__(line)
        for user in user_list:
            if re.match(
                f"(.*){user}(.*)",
                self.content,
            ):
                self.user = user
                return

        raise ValueError("invalid format")


class MinecraftPlayerListLog(MinecraftLog):
    DOMAIN = "net.minecraft.server.players.PlayerList/"
    user: str
    ip: str
    port: int
    position: str

    def __init__(self, line: str) -> None:
        super().__init__(line)
        if self.DOMAIN != self.domain:
            raise ValueError(f"This log isn't player list: {line}")
        match = re.match(
            "(.*)\[\/(\d+\.\d+\.\d+\.\d+):(\d+)].*\((.*)\)",
            self.content,
        )

        self.user = match.group(1)
        self.ip = match.group(2)
        self.port = int(match.group(3))
        self.position = match.group(4)


class MinecraftLogParser:
    _user_list: list[str]

    def __init__(self, user_list: list[str]) -> None:
        self._user_list = user_list.copy()

    def read(self, file_path: str) -> list[MinecraftLog]:
        logs = []
        with open(file_path, mode="r") as file:
            for line in file.readlines():
                try:
                    line_log = MinecraftLog(line)

                    if line_log.domain == MinecraftPlayerListLog.DOMAIN:
                        player_list_log = MinecraftPlayerListLog(line)
                        logs.append(player_list_log)
                        self._user_list.append(player_list_log.user)
                        continue

                    try:
                        user_log = MinecraftUserLog(line, self._user_list)
                        logs.append(user_log)
                    except ValueError:
                        logs.append(line_log)

                except ValueError:
                    pass
        return logs


class MinecraftLogObserver:
    __users: list[str] = []
    __login_callback: [[str], None]
    __logout_callback: Callable[[str], None]

    __latest_log: str

    def __init__(
        self,
        login_callback: Callable[[str], None],
        logout_callback: Callable[[str], None],
    ) -> None:
        self.__login_callback = login_callback
        self.__logout_callback = logout_callback

    def observe(
        self, log_path: str, backup_path: str | None = None, interval: float = 1.0
    ):
        if os.path.exists(log_path):
            if backup_path:
                os.rename(log_path, backup_path)
            else:
                os.remove(log_path)

        open(log_path, mode="w").close()

        self.__latest_log = None
        while True:
            if os.path.exists(log_path):
                self.analyze(log_path)
            time.sleep(interval)

    def analyze(self, log_path: str):
        parser = MinecraftLogParser(self.__users)
        logs = parser.read(log_path)
        latest_only_logs = logs.copy()
        if self.__latest_log is not None:
            for log in logs:
                latest_only_logs.remove(log)
                if log.line == self.__latest_log:
                    break

        for log in latest_only_logs:
            if isinstance(log, MinecraftPlayerListLog):
                if log.user not in self.__users:
                    self.__users.append(log.user)
                    self.__login_callback(log.user)

            if isinstance(log, MinecraftUserLog):
                if "left the game" in log.content:
                    self.__users.remove(log.user)
                    self.__logout_callback(log.user)

            self.__latest_log = log.line


if __name__ == "__main__":
    user_map = {}
    user_map_str = os.environ["USER_MAP"]
    for key_value in user_map_str.split(","):
        user_map[key_value.split(":")[0]] = key_value.split(":")[1]

    def login_callback(user: str):
        discord_id = user_map.get(user)
        requests.post(
            os.environ["WEBHOOK_URL"],
            {
                "content": f"<@{discord_id}>こんにちは、{user}！Minecraftの世界へようこそ！一緒に冒険し、楽しい時間を過ごしましょう！"
            },
        )

    def logout_callback(user: str):
        discord_id = user_map.get(user)
        requests.post(
            os.environ["WEBHOOK_URL"],
            {"content": f"<@{discord_id}>さようなら、{user}！お疲れ様、また来てね！"},
        )

    observer = MinecraftLogObserver(
        login_callback=login_callback,
        logout_callback=logout_callback,
    )
    observer.observe("logs/latest.log", "logs/latest.bak")
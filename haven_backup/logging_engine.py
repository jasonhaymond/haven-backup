"""Dual text + JSON-lines logging, with log levels."""

import json
import os
from datetime import datetime, timezone

DEFAULT_LOGS_PATH = os.path.expanduser("~/.haven_backup/logs")


class LoggingEngine:
    LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

    def __init__(self, logs_path: str = DEFAULT_LOGS_PATH):
        self.logs_path = os.path.expanduser(logs_path)
        os.makedirs(self.logs_path, exist_ok=True)

        self.log_files = {
            "backup": os.path.join(self.logs_path, "backup.log"),
            "restore": os.path.join(self.logs_path, "restore.log"),
            "error": os.path.join(self.logs_path, "error.log"),
        }
        self.json_log = os.path.join(self.logs_path, "structured_logs.json")

    @staticmethod
    def _timestamp():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def log(self, log_type: str, level: str, message: str):
        if level not in self.LEVELS:
            level = "INFO"

        log_file = self.log_files.get(log_type, self.log_files["backup"])
        with open(log_file, "a") as f:
            f.write(f"[{self._timestamp()}] [{level}] {message}\n")

        entry = {"timestamp": self._timestamp(), "type": log_type, "level": level, "message": message}
        with open(self.json_log, "a") as f:
            f.write(json.dumps(entry) + "\n")

        if level == "ERROR" and log_type != "error":
            with open(self.log_files["error"], "a") as f:
                f.write(f"[{self._timestamp()}] [{level}] [{log_type}] {message}\n")

    def debug(self, log_type, message):
        self.log(log_type, "DEBUG", message)

    def info(self, log_type, message):
        self.log(log_type, "INFO", message)

    def warning(self, log_type, message):
        self.log(log_type, "WARNING", message)

    def error(self, log_type, message):
        self.log(log_type, "ERROR", message)

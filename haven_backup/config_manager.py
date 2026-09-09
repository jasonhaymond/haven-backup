"""Reads/writes ~/.haven_backup/config.json -- the single source of config truth."""

import json
import os
from datetime import datetime

DEFAULT_CONFIG_FILE = os.path.expanduser("~/.haven_backup/config.json")


def default_config() -> dict:
    return {
        "backup_paths": [],
        "exclude_patterns": [],
        "destination": {
            "type": "local",
            "path": os.path.expanduser("~/.haven_backup/haven_backup_repo"),
        },
        "auto_update_enabled": False,
        "update_channel": "main",
        "retention_policy": {"full": 3, "incremental": 7},
        "last_update_time": None,
    }


class ConfigManager:
    def __init__(self, config_file: str = None):
        self.config_file = config_file or DEFAULT_CONFIG_FILE
        self._config = {}
        self._load()

    # -----------------------------
    # Load / save
    # -----------------------------
    def _load(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f:
                self._config = json.load(f)
            # Fill in any keys added since this config was written.
            for key, value in default_config().items():
                self._config.setdefault(key, value)
        else:
            self._config = default_config()
            self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        tmp_file = self.config_file + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(self._config, f, indent=2, default=str)
        os.replace(tmp_file, self.config_file)
        try:
            os.chmod(self.config_file, 0o600)
        except (AttributeError, NotImplementedError, OSError):
            pass

    def as_dict(self) -> dict:
        return dict(self._config)

    # -----------------------------
    # Backup paths / excludes
    # -----------------------------
    def get_backup_paths(self):
        return list(self._config.get("backup_paths", []))

    def set_backup_paths(self, paths):
        self._config["backup_paths"] = list(paths)
        self._save()

    def get_exclude_patterns(self):
        return list(self._config.get("exclude_patterns", []))

    def set_exclude_patterns(self, patterns):
        self._config["exclude_patterns"] = list(patterns)
        self._save()

    # -----------------------------
    # Destination
    # -----------------------------
    def get_destination(self) -> dict:
        return dict(self._config.get("destination", default_config()["destination"]))

    def set_destination_local(self, path: str):
        self._config["destination"] = {"type": "local", "path": path}
        self._save()

    def set_destination_sftp(
        self, host, username, remote_path, port=22, key_path=None,
        password=None, auto_add_host_key=False,
    ):
        self._config["destination"] = {
            "type": "sftp",
            "host": host,
            "username": username,
            "remote_path": remote_path,
            "port": port,
            "key_path": key_path,
            "password": password,
            "auto_add_host_key": auto_add_host_key,
        }
        self._save()

    # -----------------------------
    # Retention
    # -----------------------------
    def get_retention_policy(self):
        return dict(self._config.get("retention_policy", default_config()["retention_policy"]))

    def set_retention_policy(self, full: int, incremental: int):
        self._config["retention_policy"] = {"full": full, "incremental": incremental}
        self._save()

    # -----------------------------
    # Auto-update (of the Haven Backup code itself, via git)
    # -----------------------------
    def get_auto_update_enabled(self):
        return self._config.get("auto_update_enabled", False)

    def set_auto_update(self, enabled: bool):
        self._config["auto_update_enabled"] = enabled
        self._save()

    def get_update_channel(self):
        return self._config.get("update_channel", "main")

    def set_update_channel(self, channel: str):
        self._config["update_channel"] = channel
        self._save()

    def get_last_update_time(self):
        t = self._config.get("last_update_time")
        if t:
            try:
                return datetime.fromisoformat(t)
            except ValueError:
                return None
        return None

    def set_last_update_time(self, dt: datetime):
        self._config["last_update_time"] = dt.isoformat()
        self._save()

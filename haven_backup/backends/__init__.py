"""Storage backends: where an encrypted, deduplicated repo actually lives."""

from haven_backup.backends.base import StorageBackend
from haven_backup.backends.local_backend import LocalBackend
from haven_backup.backends.sftp_backend import SFTPBackend

__all__ = ["StorageBackend", "LocalBackend", "SFTPBackend", "build_backend"]


def build_backend(destination: dict) -> StorageBackend:
    """Construct the right backend from a config['destination'] dict."""
    dest_type = destination.get("type", "local")

    if dest_type == "local":
        return LocalBackend(destination["path"])

    if dest_type == "sftp":
        return SFTPBackend(
            host=destination["host"],
            username=destination["username"],
            remote_path=destination["remote_path"],
            port=destination.get("port", 22),
            key_path=destination.get("key_path"),
            password=destination.get("password"),
            auto_add_host_key=destination.get("auto_add_host_key", False),
        )

    raise ValueError(f"Unknown destination type: {dest_type!r}")

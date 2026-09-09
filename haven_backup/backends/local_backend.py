import os
import shutil
from typing import List

from haven_backup.backends.base import StorageBackend


class LocalBackend(StorageBackend):
    """Repo lives on a local path -- which may itself be a mounted NFS/SMB/sshfs share."""

    def __init__(self, root_path: str):
        self.root_path = os.path.expanduser(root_path)
        os.makedirs(self.root_path, exist_ok=True)

    def _abs(self, relpath: str) -> str:
        return os.path.join(self.root_path, *relpath.split("/"))

    def exists(self, relpath: str) -> bool:
        return os.path.exists(self._abs(relpath))

    def read(self, relpath: str) -> bytes:
        with open(self._abs(relpath), "rb") as f:
            return f.read()

    def write(self, relpath: str, data: bytes) -> None:
        abs_path = self._abs(relpath)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        tmp_path = abs_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, abs_path)  # atomic on POSIX and Windows

    def remove(self, relpath: str) -> None:
        abs_path = self._abs(relpath)
        if os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        elif os.path.exists(abs_path):
            os.remove(abs_path)

    def list_dir(self, relpath: str) -> List[str]:
        abs_path = self._abs(relpath)
        if not os.path.exists(abs_path):
            return []
        return os.listdir(abs_path)

    def disk_usage(self):
        return shutil.disk_usage(self.root_path)

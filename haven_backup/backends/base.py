"""Backend interface every storage destination (local disk, SFTP, ...) implements.

All paths passed to a backend are POSIX-style relative paths inside the repo,
e.g. "data/<hash>.enc" or "snapshots/full_20260101000000.json" -- never absolute
host paths. Writes must be atomic: a reader must never observe a partially
written file, even if the process is killed mid-write.
"""

from abc import ABC, abstractmethod
from typing import List


class StorageBackend(ABC):
    @abstractmethod
    def exists(self, relpath: str) -> bool:
        ...

    @abstractmethod
    def read(self, relpath: str) -> bytes:
        ...

    @abstractmethod
    def write(self, relpath: str, data: bytes) -> None:
        ...

    @abstractmethod
    def remove(self, relpath: str) -> None:
        ...

    @abstractmethod
    def list_dir(self, relpath: str) -> List[str]:
        """Return entry names directly under relpath, or [] if it doesn't exist."""
        ...

    @abstractmethod
    def disk_usage(self):
        """Return (total, used, free) in bytes, or None if not supported."""
        ...

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

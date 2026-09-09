import io
import os
import posixpath
import time
from typing import List

import paramiko

from haven_backup.backends.base import StorageBackend

RETRYABLE_EXCEPTIONS = (EOFError, ConnectionError, OSError, paramiko.SSHException)


class SFTPBackend(StorageBackend):
    """Repo lives on a remote host over SFTP -- no mount required.

    Auth is key-based by default (recommended: a dedicated key restricted to the
    backup account, see docs/SFTP_SETUP.md). A password is supported as a fallback
    but key-based auth should be preferred for unattended server backups.
    """

    def __init__(
        self,
        host: str,
        username: str,
        remote_path: str,
        port: int = 22,
        key_path: str = None,
        password: str = None,
        auto_add_host_key: bool = False,
        max_retries: int = 3,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.key_path = os.path.expanduser(key_path) if key_path else None
        self.password = password
        self.auto_add_host_key = auto_add_host_key
        self.max_retries = max_retries
        self.remote_root = remote_path.rstrip("/") or "/"

        self._client = None
        self._sftp = None
        self._dirs_ensured = set()

    # -----------------------------
    # Connection management
    # -----------------------------
    def _connect(self):
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if self.auto_add_host_key:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())

        connect_kwargs = {"port": self.port, "username": self.username, "timeout": 30}
        if self.key_path:
            connect_kwargs["key_filename"] = self.key_path
        if self.password:
            connect_kwargs["password"] = self.password

        client.connect(self.host, **connect_kwargs)

        self._client = client
        self._sftp = client.open_sftp()
        self._dirs_ensured = set()

    def _ensure_connected(self):
        if self._sftp is None:
            self._connect()

    def _with_retry(self, func, *args, **kwargs):
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._ensure_connected()
                return func(*args, **kwargs)
            except RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                self.close()
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 10))
        raise ConnectionError(
            f"SFTP operation failed after {self.max_retries} attempts against "
            f"{self.username}@{self.host}:{self.port}: {last_exc}"
        ) from last_exc

    def close(self) -> None:
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception:
                pass
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._sftp = None
        self._client = None

    # -----------------------------
    # Path helpers
    # -----------------------------
    def _remote(self, relpath: str) -> str:
        return posixpath.join(self.remote_root, *relpath.split("/"))

    def _makedirs(self, remote_dir: str) -> None:
        if remote_dir in self._dirs_ensured or remote_dir in ("", "/", "."):
            return
        parent = posixpath.dirname(remote_dir)
        if parent and parent != remote_dir:
            self._makedirs(parent)
        try:
            self._sftp.mkdir(remote_dir)
        except IOError:
            pass  # already exists (or a race with another process) -- fine either way
        self._dirs_ensured.add(remote_dir)

    # -----------------------------
    # StorageBackend interface
    # -----------------------------
    def exists(self, relpath: str) -> bool:
        def _op():
            try:
                self._sftp.stat(self._remote(relpath))
                return True
            except FileNotFoundError:
                return False

        return self._with_retry(_op)

    def read(self, relpath: str) -> bytes:
        def _op():
            buf = io.BytesIO()
            self._sftp.getfo(self._remote(relpath), buf)
            return buf.getvalue()

        return self._with_retry(_op)

    def write(self, relpath: str, data: bytes) -> None:
        remote_path = self._remote(relpath)
        tmp_path = remote_path + ".tmp"

        def _op():
            self._makedirs(posixpath.dirname(remote_path))
            self._sftp.putfo(io.BytesIO(data), tmp_path, confirm=True)
            try:
                self._sftp.remove(remote_path)
            except FileNotFoundError:
                pass
            self._sftp.posix_rename(tmp_path, remote_path)

        self._with_retry(_op)

    def remove(self, relpath: str) -> None:
        remote_path = self._remote(relpath)

        def _op():
            try:
                self._sftp.remove(remote_path)
            except FileNotFoundError:
                pass

        self._with_retry(_op)

    def list_dir(self, relpath: str) -> List[str]:
        remote_path = self._remote(relpath)

        def _op():
            try:
                return self._sftp.listdir(remote_path)
            except FileNotFoundError:
                return []

        return self._with_retry(_op)

    def disk_usage(self):
        return None  # SFTP has no portable free-space query; skipped in health checks

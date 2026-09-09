from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow)


class SSHCredential(SQLModel, table=True):
    """A reusable SSH identity: reaches a Borg repo host (via `borg`'s own BORG_RSH)
    or a client host (via paramiko, to trigger borgmatic there) -- same model, either use.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    hostname: str
    port: int = Field(default=22)
    username: str
    private_key_encrypted: bytes
    key_passphrase_encrypted: Optional[bytes] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class ClientHost(SQLModel, table=True):
    """A machine that runs borgmatic locally and can be told to back up now."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    ssh_credential_id: int = Field(foreign_key="sshcredential.id")
    borgmatic_config_path: str = Field(default="/etc/borgmatic/config.yaml")
    notes: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class Repo(SQLModel, table=True):
    """A Borg repository (destination). Monitored/pruned directly by the portal
    shelling out to its own local `borg`, over SSH via BORG_RSH -- no access to
    the client host is needed for this. `client_host_id` just records which
    host creates archives into it, for the dashboard and the "backup now" action.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    repo_url: str  # e.g. ssh://user@backup-host:22/./path/to/repo
    ssh_credential_id: int = Field(foreign_key="sshcredential.id")
    passphrase_encrypted: bytes
    client_host_id: Optional[int] = Field(default=None, foreign_key="clienthost.id")

    keep_daily: int = Field(default=7)
    keep_weekly: int = Field(default=4)
    keep_monthly: int = Field(default=6)
    keep_yearly: int = Field(default=1)

    expected_interval_hours: int = Field(default=26)  # flag stale if no new archive within this
    notes: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class BackupRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repo.id", index=True)
    host_id: Optional[int] = Field(default=None, foreign_key="clienthost.id")
    triggered_by: str = Field(default="manual")  # manual | scheduled
    status: str = Field(default="running")  # running | success | failed
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = Field(default=None)
    output_log: str = Field(default="")


class PruneRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repo.id", index=True)
    triggered_by: str = Field(default="manual")  # manual | scheduled
    dry_run: bool = Field(default=False)
    status: str = Field(default="running")  # running | success | failed
    archives_deleted: int = Field(default=0)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = Field(default=None)
    output_log: str = Field(default="")


class CheckRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repo.id", index=True)
    triggered_by: str = Field(default="manual")  # manual | scheduled
    status: str = Field(default="running")  # running | success | failed
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = Field(default=None)
    output_log: str = Field(default="")


class RepoStatusSnapshot(SQLModel, table=True):
    """A point-in-time `borg info` reading, for dashboard trend charts and staleness checks."""

    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repo.id", index=True)
    captured_at: datetime = Field(default_factory=utcnow)
    num_archives: Optional[int] = Field(default=None)
    original_size: Optional[int] = Field(default=None)
    compressed_size: Optional[int] = Field(default=None)
    deduplicated_size: Optional[int] = Field(default=None)
    last_archive_name: Optional[str] = Field(default=None)
    last_archive_time: Optional[datetime] = Field(default=None)
    ok: bool = Field(default=True)
    error: Optional[str] = Field(default=None)

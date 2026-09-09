"""Runs `borg` locally against a repo's ssh:// URL.

No paramiko involved here: when given an ssh://user@host/path repo URL, `borg`
opens its own SSH connection (the same way `git` does for a git+ssh remote),
via the BORG_RSH environment variable. We only ever need to hand it a
decrypted private key file (written locked-down, used once, removed
immediately after) and the repo passphrase as an env var.

Field-level parsing of `borg info`/`borg list` JSON and `borg prune` text
output is best-effort and defensive by design: `borg`'s exact output shape has
drifted across 1.x/2.x releases, and this hasn't been validated against a
live repository in this environment (see docs/BORG_COMPATIBILITY.md). The raw
stdout/stderr is always preserved on the run record even when a specific
field can't be extracted, so nothing is silently lost.
"""

import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from app import config


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class BorgRunError(RuntimeError):
    pass


def _materialize_key(private_key_pem: str) -> Path:
    config.SSH_KEY_WORKDIR.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(dir=str(config.SSH_KEY_WORKDIR), prefix="id_", suffix=".key")
    path = Path(raw_path)
    with os.fdopen(fd, "w") as f:
        f.write(private_key_pem)
        if not private_key_pem.endswith("\n"):
            f.write("\n")
    try:
        os.chmod(path, 0o600)
    except (AttributeError, NotImplementedError, OSError):
        pass
    return path


def run_borg(
    args: list,
    passphrase: str,
    ssh_private_key_pem: str,
    ssh_port: int = 22,
    timeout: int = None,
) -> CommandResult:
    """args is the full borg argv tail, e.g. ["info", "--json", repo_url]."""
    key_path = _materialize_key(ssh_private_key_pem)
    try:
        env = os.environ.copy()
        env["BORG_PASSPHRASE"] = passphrase
        env["BORG_RSH"] = (
            f"ssh -i {shlex.quote(str(key_path))} -p {ssh_port} "
            f"-o StrictHostKeyChecking=accept-new -o BatchMode=yes "
            f"{os.environ.get('HAVEN_BORG_SSH_EXTRA_OPTS', '')}"
        ).strip()
        env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"

        try:
            proc = subprocess.run(
                [config.BORG_BINARY, *args],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout or config.COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as e:
            raise BorgRunError(
                f"'{config.BORG_BINARY}' not found. Is borg installed in the portal's environment?"
            ) from e
        except subprocess.TimeoutExpired as e:
            return CommandResult(exit_code=124, stdout=e.stdout or "", stderr=(e.stderr or "") + "\n[timed out]")

        return CommandResult(proc.returncode, proc.stdout, proc.stderr)
    finally:
        key_path.unlink(missing_ok=True)


# -----------------------------
# Command builders
# -----------------------------
def info_args(repo_url: str) -> list:
    return ["info", "--json", repo_url]


def list_args(repo_url: str) -> list:
    return ["list", "--json", repo_url]


def check_args(repo_url: str) -> list:
    return ["check", repo_url]


def prune_args(repo_url: str, keep_daily: int, keep_weekly: int, keep_monthly: int, keep_yearly: int, dry_run: bool) -> list:
    args = ["prune", "--list", "--stats"]
    if dry_run:
        args.append("--dry-run")
    args += [
        f"--keep-daily={keep_daily}",
        f"--keep-weekly={keep_weekly}",
        f"--keep-monthly={keep_monthly}",
        f"--keep-yearly={keep_yearly}",
        repo_url,
    ]
    return args


# -----------------------------
# Output parsing (best-effort, never raises on unexpected shape)
# -----------------------------
@dataclass
class RepoInfo:
    ok: bool
    num_archives: Optional[int] = None
    original_size: Optional[int] = None
    compressed_size: Optional[int] = None
    deduplicated_size: Optional[int] = None
    error: Optional[str] = None


def parse_info(result: CommandResult) -> RepoInfo:
    if not result.ok:
        return RepoInfo(ok=False, error=result.stderr.strip() or f"borg info exited {result.exit_code}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return RepoInfo(ok=False, error=f"Could not parse `borg info --json` output: {e}")

    stats = data.get("cache", {}).get("stats", {})
    return RepoInfo(
        ok=True,
        original_size=stats.get("total_size"),
        compressed_size=stats.get("total_csize"),
        deduplicated_size=stats.get("unique_csize") or stats.get("unique_size"),
        num_archives=data.get("repository", {}).get("archive_count") or stats.get("total_chunks"),
    )


@dataclass
class Archive:
    name: str
    time: Optional[datetime]


@dataclass
class ArchiveList:
    ok: bool
    archives: list = field(default_factory=list)
    error: Optional[str] = None

    @property
    def latest(self) -> Optional[Archive]:
        timed = [a for a in self.archives if a.time is not None]
        if not timed:
            return self.archives[-1] if self.archives else None
        return max(timed, key=lambda a: a.time)


def _parse_archive_time(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_list(result: CommandResult) -> ArchiveList:
    if not result.ok:
        return ArchiveList(ok=False, error=result.stderr.strip() or f"borg list exited {result.exit_code}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return ArchiveList(ok=False, error=f"Could not parse `borg list --json` output: {e}")

    archives = []
    for entry in data.get("archives", []):
        name = entry.get("name", "?")
        raw_time = entry.get("time") or entry.get("start")
        archives.append(Archive(name=name, time=_parse_archive_time(raw_time)))
    return ArchiveList(ok=True, archives=archives)


_PRUNE_DELETE_LINE = re.compile(r"^(Would prune:|Pruning archive)", re.MULTILINE)


@dataclass
class PruneResult:
    ok: bool
    archives_deleted: int
    error: Optional[str] = None


def parse_prune(result: CommandResult) -> PruneResult:
    if not result.ok:
        return PruneResult(ok=False, archives_deleted=0, error=result.stderr.strip() or f"borg prune exited {result.exit_code}")
    combined = result.stdout + "\n" + result.stderr  # borg prune writes progress to stderr in some versions
    count = len(_PRUNE_DELETE_LINE.findall(combined))
    return PruneResult(ok=True, archives_deleted=count)

"""Ties Repo DB records to borg_runner calls, recording status snapshots, prune runs,
and check runs. `prune`/`check` are split into create_pending_*/execute_* so a router
can hand back a pollable id immediately and do the actual (possibly slow) borg
invocation in a background task -- refresh_status is fast enough to just run inline.
"""

from datetime import datetime, timezone

from sqlmodel import Session

from app import borg_runner, crypto
from app.models import CheckRun, PruneRun, Repo, RepoStatusSnapshot, SSHCredential


def _repo_credentials(session: Session, repo: Repo):
    cred = session.get(SSHCredential, repo.ssh_credential_id)
    private_key_pem = crypto.decrypt(cred.private_key_encrypted)
    passphrase = crypto.decrypt(repo.passphrase_encrypted)
    return cred, private_key_pem, passphrase


def refresh_status(session: Session, repo: Repo) -> RepoStatusSnapshot:
    cred, key_pem, passphrase = _repo_credentials(session, repo)

    info_result = borg_runner.run_borg(borg_runner.info_args(repo.repo_url), passphrase, key_pem, cred.port)
    info = borg_runner.parse_info(info_result)

    snapshot = RepoStatusSnapshot(
        repo_id=repo.id,
        ok=info.ok,
        error=info.error,
        num_archives=info.num_archives,
        original_size=info.original_size,
        compressed_size=info.compressed_size,
        deduplicated_size=info.deduplicated_size,
    )

    if info.ok:
        list_result = borg_runner.run_borg(borg_runner.list_args(repo.repo_url), passphrase, key_pem, cred.port)
        archive_list = borg_runner.parse_list(list_result)
        if archive_list.ok:
            latest = archive_list.latest
            if latest:
                snapshot.last_archive_name = latest.name
                snapshot.last_archive_time = latest.time
            if snapshot.num_archives is None:
                snapshot.num_archives = len(archive_list.archives)
        else:
            snapshot.ok = False
            snapshot.error = archive_list.error

    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


# -----------------------------
# Prune
# -----------------------------
def create_pending_prune(session: Session, repo: Repo, dry_run: bool, triggered_by: str = "manual") -> PruneRun:
    run = PruneRun(repo_id=repo.id, dry_run=dry_run, triggered_by=triggered_by, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def execute_prune(session: Session, run: PruneRun, repo: Repo) -> PruneRun:
    cred, key_pem, passphrase = _repo_credentials(session, repo)

    args = borg_runner.prune_args(
        repo.repo_url, repo.keep_daily, repo.keep_weekly, repo.keep_monthly, repo.keep_yearly, run.dry_run
    )
    result = borg_runner.run_borg(args, passphrase, key_pem, cred.port)
    parsed = borg_runner.parse_prune(result)

    run.status = "success" if parsed.ok else "failed"
    run.archives_deleted = parsed.archives_deleted
    shown_args = " ".join(a for a in args if a != repo.repo_url)
    run.output_log = f"$ borg {shown_args} <repo>\n{result.stdout}\n{result.stderr}".strip()
    run.finished_at = datetime.now(timezone.utc)

    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def run_prune(session: Session, repo: Repo, dry_run: bool, triggered_by: str = "manual") -> PruneRun:
    """Synchronous convenience wrapper for callers that don't need the background split."""
    run = create_pending_prune(session, repo, dry_run, triggered_by)
    return execute_prune(session, run, repo)


# -----------------------------
# Check
# -----------------------------
def create_pending_check(session: Session, repo: Repo, triggered_by: str = "manual") -> CheckRun:
    run = CheckRun(repo_id=repo.id, triggered_by=triggered_by, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def execute_check(session: Session, run: CheckRun, repo: Repo) -> CheckRun:
    cred, key_pem, passphrase = _repo_credentials(session, repo)
    result = borg_runner.run_borg(borg_runner.check_args(repo.repo_url), passphrase, key_pem, cred.port)

    run.status = "success" if result.ok else "failed"
    run.output_log = f"$ borg check <repo>\n{result.stdout}\n{result.stderr}".strip()
    run.finished_at = datetime.now(timezone.utc)

    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def run_check(session: Session, repo: Repo, triggered_by: str = "manual") -> CheckRun:
    run = create_pending_check(session, repo, triggered_by)
    return execute_check(session, run, repo)

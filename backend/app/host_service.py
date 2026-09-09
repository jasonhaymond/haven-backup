"""Remotely triggers a borgmatic `create` run on a client host over SSH.

Split into create_pending_run (fast, synchronous -- gives the caller an id to
poll immediately) and execute_run (the actual SSH exec, which can take a long
time and is meant to be called from a background task).
"""

import shlex
from datetime import datetime, timezone

from sqlmodel import Session

from app import crypto, ssh_exec
from app.models import BackupRun, ClientHost, SSHCredential


def create_pending_run(session: Session, host: ClientHost, repo_id: int, triggered_by: str = "manual") -> BackupRun:
    run = BackupRun(repo_id=repo_id, host_id=host.id, triggered_by=triggered_by, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def execute_run(session: Session, run: BackupRun, host: ClientHost) -> BackupRun:
    cred = session.get(SSHCredential, host.ssh_credential_id)
    key_pem = crypto.decrypt(cred.private_key_encrypted)
    key_passphrase = crypto.decrypt(cred.key_passphrase_encrypted) if cred.key_passphrase_encrypted else None

    # Deliberately `create` only, never the full `borgmatic` action list: retention is
    # owned centrally by this portal (see repo_service.run_prune), so a client-side
    # borgmatic config running its own `prune` on a different schedule/policy would
    # otherwise fight the portal over what gets kept. See docs/BORGMATIC_INTEGRATION.md.
    command = f"borgmatic --config {shlex.quote(host.borgmatic_config_path)} create --stats"

    try:
        exit_code, out, err = ssh_exec.exec_command(
            cred.hostname, cred.port, cred.username, key_pem, key_passphrase, command
        )
        run.status = "success" if exit_code == 0 else "failed"
        run.output_log = f"$ {command}\n{out}\n{err}".strip()
    except ssh_exec.SSHExecError as e:
        run.status = "failed"
        run.output_log = f"$ {command}\n{e}"

    run.finished_at = datetime.now(timezone.utc)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def trigger_backup(session: Session, host: ClientHost, repo_id: int, triggered_by: str = "manual") -> BackupRun:
    """Synchronous convenience wrapper (create + execute in one call) for callers
    that don't need the background-task split, e.g. the scheduler."""
    run = create_pending_run(session, host, repo_id, triggered_by)
    return execute_run(session, run, host)

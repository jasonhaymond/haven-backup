import json

from app import borg_runner, crypto, repo_service
from app.models import Repo, SSHCredential

INFO_JSON = json.dumps({
    "repository": {"id": "abc123"},
    "cache": {"stats": {
        "total_chunks": 4200, "total_csize": 5_000_000_000,
        "total_size": 20_000_000_000, "unique_csize": 1_200_000_000, "unique_size": 3_000_000_000,
    }},
})

LIST_JSON = json.dumps({
    "archives": [
        {"name": "host1-2026-01-01T02:00:00", "id": "id1", "time": "2026-01-01T02:00:00.000000"},
        {"name": "host1-2026-01-02T02:00:00", "id": "id2", "time": "2026-01-02T02:00:00.000000"},
    ],
})

PRUNE_DRY_RUN_OUTPUT = """
Keeping archive (rule: daily #1):  host1-2026-01-02T02:00:00
Would prune:                       host1-2025-12-01T02:00:00
Would prune:                       host1-2025-11-01T02:00:00
"""


def _make_repo(db_session) -> Repo:
    cred = SSHCredential(
        name="backup-host", hostname="backup.example.com", port=2222, username="haven",
        private_key_encrypted=crypto.encrypt("fake-private-key-pem"),
    )
    db_session.add(cred)
    db_session.commit()
    db_session.refresh(cred)

    repo = Repo(
        name="proxmox1", repo_url="ssh://haven@backup.example.com/./repo",
        ssh_credential_id=cred.id, passphrase_encrypted=crypto.encrypt("repo-passphrase"),
        keep_daily=7, keep_weekly=4, keep_monthly=6, keep_yearly=1,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


def test_refresh_status_healthy_repo(db_session, monkeypatch):
    repo = _make_repo(db_session)

    def fake_run_borg(args, passphrase, ssh_private_key_pem, ssh_port, timeout=None):
        assert passphrase == "repo-passphrase"
        assert ssh_private_key_pem == "fake-private-key-pem"
        assert ssh_port == 2222
        if args[0] == "info":
            return borg_runner.CommandResult(0, INFO_JSON, "")
        if args[0] == "list":
            return borg_runner.CommandResult(0, LIST_JSON, "")
        raise AssertionError(f"unexpected args {args}")

    monkeypatch.setattr(borg_runner, "run_borg", fake_run_borg)

    snapshot = repo_service.refresh_status(db_session, repo)
    assert snapshot.ok is True
    assert snapshot.last_archive_name == "host1-2026-01-02T02:00:00"
    assert snapshot.deduplicated_size == 1_200_000_000


def test_refresh_status_records_failure_without_raising(db_session, monkeypatch):
    repo = _make_repo(db_session)

    def fake_run_borg(args, passphrase, ssh_private_key_pem, ssh_port, timeout=None):
        return borg_runner.CommandResult(2, "", "connection refused")

    monkeypatch.setattr(borg_runner, "run_borg", fake_run_borg)

    snapshot = repo_service.refresh_status(db_session, repo)
    assert snapshot.ok is False
    assert "connection refused" in snapshot.error


def test_run_prune_dry_run_records_count_without_deleting(db_session, monkeypatch):
    repo = _make_repo(db_session)

    def fake_run_borg(args, passphrase, ssh_private_key_pem, ssh_port, timeout=None):
        assert "--dry-run" in args
        assert "--keep-daily=7" in args
        return borg_runner.CommandResult(0, PRUNE_DRY_RUN_OUTPUT, "")

    monkeypatch.setattr(borg_runner, "run_borg", fake_run_borg)

    run = repo_service.run_prune(db_session, repo, dry_run=True)
    assert run.status == "success"
    assert run.dry_run is True
    assert run.archives_deleted == 2


def test_run_check_records_failure_output(db_session, monkeypatch):
    repo = _make_repo(db_session)

    def fake_run_borg(args, passphrase, ssh_private_key_pem, ssh_port, timeout=None):
        assert args[0] == "check"
        return borg_runner.CommandResult(1, "", "Repository check failed")

    monkeypatch.setattr(borg_runner, "run_borg", fake_run_borg)

    run = repo_service.run_check(db_session, repo)
    assert run.status == "failed"
    assert "Repository check failed" in run.output_log

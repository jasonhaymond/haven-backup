import pytest

from app import crypto
from app.models import BackupRun, CheckRun, PruneRun, Repo, SSHCredential


@pytest.fixture(autouse=True)
def _logged_in(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    return client


def _make_repo(db_session, name="repo-a"):
    cred = SSHCredential(
        name=f"{name}-cred", hostname="h", port=22, username="u",
        private_key_encrypted=crypto.encrypt("key"),
    )
    db_session.add(cred)
    db_session.commit()
    db_session.refresh(cred)

    repo = Repo(name=name, repo_url="ssh://h/./repo", ssh_credential_id=cred.id, passphrase_encrypted=crypto.encrypt("pw"))
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


def test_list_backup_runs_filters_by_repo(client, db_session):
    repo_a = _make_repo(db_session, "repo-a")
    repo_b = _make_repo(db_session, "repo-b")
    db_session.add(BackupRun(repo_id=repo_a.id, status="success"))
    db_session.add(BackupRun(repo_id=repo_b.id, status="failed"))
    db_session.commit()

    response = client.get(f"/api/runs/backups?repo_id={repo_a.id}")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["repo_id"] == repo_a.id


def test_get_backup_run_not_found(client):
    assert client.get("/api/runs/backups/9999").status_code == 404


def test_list_prune_runs_filters_by_repo(client, db_session):
    repo_a = _make_repo(db_session, "repo-a")
    repo_b = _make_repo(db_session, "repo-b")
    db_session.add(PruneRun(repo_id=repo_a.id, status="success", dry_run=True, archives_deleted=2))
    db_session.add(PruneRun(repo_id=repo_b.id, status="success", dry_run=False, archives_deleted=1))
    db_session.commit()

    response = client.get(f"/api/runs/prunes?repo_id={repo_a.id}")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["archives_deleted"] == 2


def test_list_check_runs_filters_by_repo_and_orders_newest_first(client, db_session):
    repo_a = _make_repo(db_session, "repo-a")
    repo_b = _make_repo(db_session, "repo-b")
    first = CheckRun(repo_id=repo_a.id, status="success")
    db_session.add(first)
    db_session.commit()
    second = CheckRun(repo_id=repo_a.id, status="failed")
    db_session.add(second)
    db_session.add(CheckRun(repo_id=repo_b.id, status="success"))
    db_session.commit()

    response = client.get(f"/api/runs/checks?repo_id={repo_a.id}")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 2
    assert runs[0]["id"] == second.id  # newest first


def test_get_check_run_not_found(client):
    assert client.get("/api/runs/checks/9999").status_code == 404


def test_runs_endpoints_require_auth(client):
    client.post("/api/auth/logout")
    assert client.get("/api/runs/backups").status_code == 401
    assert client.get("/api/runs/prunes").status_code == 401
    assert client.get("/api/runs/checks").status_code == 401

import pytest


@pytest.fixture(autouse=True)
def _logged_in(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    return client


def _create_credential(client, name="backup-host"):
    response = client.post("/api/credentials", json={
        "name": name, "hostname": "backup.example.com", "port": 22,
        "username": "haven", "private_key": "-----BEGIN KEY-----\nfake\n-----END KEY-----",
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_credential_create_never_returns_private_key(client):
    body = _create_credential(client)
    assert "private_key" not in body
    assert "private_key_encrypted" not in body


def test_credential_duplicate_name_rejected(client):
    _create_credential(client)
    response = client.post("/api/credentials", json={
        "name": "backup-host", "hostname": "x", "port": 22, "username": "haven", "private_key": "key",
    })
    assert response.status_code == 409


def test_host_crud(client):
    cred = _create_credential(client)
    response = client.post("/api/hosts", json={
        "name": "proxmox1", "ssh_credential_id": cred["id"], "borgmatic_config_path": "/etc/borgmatic/config.yaml",
    })
    assert response.status_code == 200
    host_id = response.json()["id"]

    listed = client.get("/api/hosts").json()
    assert any(h["id"] == host_id for h in listed)

    deleted = client.delete(f"/api/hosts/{host_id}")
    assert deleted.status_code == 200
    assert not any(h["id"] == host_id for h in client.get("/api/hosts").json())


def test_repo_crud_and_passphrase_never_returned(client):
    cred = _create_credential(client)
    response = client.post("/api/repos", json={
        "name": "proxmox1-repo", "repo_url": "ssh://haven@backup.example.com/./repo",
        "ssh_credential_id": cred["id"], "passphrase": "super-secret-passphrase",
        "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6, "keep_yearly": 1,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert "passphrase" not in body
    assert "passphrase_encrypted" not in body

    repo_id = body["id"]
    updated = client.put(f"/api/repos/{repo_id}", json={
        "name": "proxmox1-repo", "repo_url": "ssh://haven@backup.example.com/./repo",
        "ssh_credential_id": cred["id"], "passphrase": "",
        "keep_daily": 14, "keep_weekly": 4, "keep_monthly": 6, "keep_yearly": 1,
    })
    assert updated.status_code == 200
    assert updated.json()["keep_daily"] == 14


def test_dashboard_reports_repo_with_no_snapshot_as_stale(client):
    cred = _create_credential(client)
    client.post("/api/repos", json={
        "name": "proxmox1-repo", "repo_url": "ssh://haven@backup.example.com/./repo",
        "ssh_credential_id": cred["id"], "passphrase": "secret",
    })

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    entries = dashboard.json()
    assert len(entries) == 1
    assert entries[0]["is_stale"] is True
    assert entries[0]["ok"] is None

from datetime import datetime, timedelta, timezone

import paramiko
import pytest
from sqlmodel import Session, select

from app import crypto
from app import enrollment as enr
from app.models import Enrollment, SSHCredential

_, CLIENT_PUBKEY = enr.generate_keypair("client@test")


@pytest.fixture(autouse=True)
def _logged_in(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    return client


def _backup_credential(client):
    response = client.post("/api/credentials", json={
        "name": "backup-server", "hostname": "backup.example.com", "port": 2222,
        "username": "haven", "private_key": "-----BEGIN KEY-----\nfake\n-----END KEY-----",
    })
    assert response.status_code == 200, response.text
    return response.json()


def _enroll(client, **overrides):
    cred = _backup_credential(client)
    body = {
        "name": "pve1", "address": "10.0.0.5", "backup_credential_id": cred["id"],
        "repo_base_path": "/srv/backups/haven-backup/", "source_directories": ["/etc", "/root", ""],
    } | overrides
    response = client.post("/api/enrollments", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _claim(client, token, **overrides):
    body = {
        "token": token, "hostname": "pve1.lan", "client_public_key": CLIENT_PUBKEY,
        "borgmatic_version": "1.7.7", "borgmatic_path": "/usr/bin/borgmatic",
    } | overrides
    return client.post("/api/enroll/claim", json=body)


def test_create_requires_login(client):
    client.post("/api/auth/logout")
    assert client.get("/api/enrollments").status_code == 401
    assert client.post("/api/enrollments", json={}).status_code in (401, 422)


def test_create_returns_token_once_and_stores_only_its_hash(client, test_engine):
    created = _enroll(client)
    assert created["status"] == "pending"
    assert created["repo_url"] == "ssh://haven@backup.example.com:2222/srv/backups/haven-backup/pve1"
    assert created["source_directories"] == ["/etc", "/root"]

    with Session(test_engine) as session:
        row = session.exec(select(Enrollment)).one()
        assert row.token_hash == enr.hash_token(created["token"])
        assert created["token"] not in row.token_hash

    listed = client.get("/api/enrollments").json()
    assert "token" not in listed[0]


@pytest.mark.parametrize("field,value", [
    ("name", "bad name"),
    ("repo_base_path", "relative/path"),
    ("repo_base_path", "/srv/../etc"),
    ("source_directories", ["/etc\n/evil"]),
    ("schedule", "daily\nExecStart=/bin/sh"),
    ("address", "host; rm -rf /"),
])
def test_create_rejects_unsafe_input(client, field, value):
    cred = _backup_credential(client)
    body = {
        "name": "pve1", "address": "10.0.0.5", "backup_credential_id": cred["id"],
        "repo_base_path": "/srv/backups", "source_directories": ["/etc"], field: value,
    }
    assert client.post("/api/enrollments", json=body).status_code == 422


def test_claim_creates_host_repo_and_credential(client, test_engine):
    created = _enroll(client)
    response = _claim(client, created["token"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["repo_url"] == created["repo_url"]
    assert body["backup_server_account"] == "haven@backup.example.com"
    assert body["backup_server_line"].startswith(
        'command="borg serve --restrict-to-repository /srv/backups/haven-backup/pve1",restrict ssh-ed25519 '
    )
    assert body["portal_authorized_keys_line"].startswith(
        'command="/usr/bin/borgmatic --config /etc/borgmatic/haven.yaml create --stats",restrict ssh-ed25519 '
    )
    assert "OnCalendar=*-*-* 02:00:00" in body["systemd_timer"]
    assert "ExecStart=/usr/bin/borgmatic --config /etc/borgmatic/haven.yaml create --stats" in body["systemd_service"]

    hosts = client.get("/api/hosts").json()
    repos = client.get("/api/repos").json()
    assert [h["name"] for h in hosts] == ["pve1"]
    assert hosts[0]["borgmatic_config_path"] == "/etc/borgmatic/haven.yaml"
    assert repos[0]["client_host_id"] == hosts[0]["id"]
    assert repos[0]["repo_url"] == created["repo_url"]

    with Session(test_engine) as session:
        portal_cred = session.get(SSHCredential, hosts[0]["ssh_credential_id"])
        assert (portal_cred.hostname, portal_cred.username) == ("10.0.0.5", "root")
        # The stored key is usable by the same loader "Backup now" uses.
        paramiko.Ed25519Key.from_private_key(__import__("io").StringIO(crypto.decrypt(portal_cred.private_key_encrypted)))

    listed = client.get("/api/enrollments").json()[0]
    assert listed["status"] == "claimed"
    assert listed["backup_server_line"] == body["backup_server_line"]


def test_claim_is_single_use(client):
    created = _enroll(client)
    assert _claim(client, created["token"]).status_code == 200
    assert _claim(client, created["token"]).status_code == 410


def test_claim_rejects_unknown_and_expired_tokens(client, test_engine):
    assert _claim(client, "not-a-real-token").status_code == 410

    created = _enroll(client)
    with Session(test_engine) as session:
        row = session.exec(select(Enrollment)).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.add(row)
        session.commit()
    assert _claim(client, created["token"]).status_code == 410
    assert client.get("/api/enrollments").json()[0]["status"] == "expired"


def test_revoked_enrollment_cannot_be_claimed(client):
    created = _enroll(client)
    assert client.delete(f"/api/enrollments/{created['id']}").status_code == 200
    assert _claim(client, created["token"]).status_code == 410


@pytest.mark.parametrize("key", [
    CLIENT_PUBKEY + "\nssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEvil evil@attacker",
    'no-pty,command="/bin/sh" ' + CLIENT_PUBKEY,
    "ssh-ed25519 not-base64!!",
    "ssh-rsa " + CLIENT_PUBKEY.split()[1],  # declared type doesn't match the blob
])
def test_claim_rejects_malformed_or_smuggled_public_keys(client, key):
    created = _enroll(client)
    assert _claim(client, created["token"], client_public_key=key).status_code == 422
    # A rejected claim must not burn the token.
    assert _claim(client, created["token"]).status_code == 200


def test_client_key_comment_is_replaced_not_passed_through(client):
    created = _enroll(client)
    key = CLIENT_PUBKEY.split()[0] + " " + CLIENT_PUBKEY.split()[1] + " whatever-the-client-said"
    line = _claim(client, created["token"], client_public_key=key).json()["backup_server_line"]
    assert "whatever-the-client-said" not in line
    assert line.endswith("haven-client@pve1.lan")


def test_name_collision_blocks_create_and_claim(client):
    created = _enroll(client)
    cred_id = client.get("/api/credentials").json()[0]["id"]
    client.post("/api/hosts", json={"name": "pve1", "ssh_credential_id": cred_id})
    assert _claim(client, created["token"]).status_code == 409


def test_install_script_is_public(client):
    client.post("/api/auth/logout")
    response = client.get("/api/enroll/install.sh")
    assert response.status_code == 200
    assert response.text.startswith("#!/usr/bin/env bash")
    assert 'main "$@"' in response.text


def test_borgmatic_config_format_follows_version():
    old = enr.render_borgmatic_config("1.7.7", "pve1", "ssh://h/r", "pw", ["/etc", "/root"])
    new = enr.render_borgmatic_config("borgmatic 1.8.8", "pve1", "ssh://h/r", "pw", ["/etc"])
    assert "location:\n  source_directories:\n    - \"/etc\"\n    - \"/root\"\n" in old
    assert "storage:\n  encryption_passphrase: \"pw\"" in old
    assert "location:" not in new
    assert "source_directories:\n  - \"/etc\"\nrepositories:\n  - path: \"ssh://h/r\"" in new
    settings = [line for line in (old + new).splitlines() if not line.startswith("#")]
    assert not any("keep_" in line for line in settings)

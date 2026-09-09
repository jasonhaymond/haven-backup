from app import crypto, host_service, ssh_exec
from app.models import ClientHost, SSHCredential


def _make_host(db_session) -> ClientHost:
    cred = SSHCredential(
        name="proxmox1-ssh", hostname="proxmox1.lan", port=22, username="root",
        private_key_encrypted=crypto.encrypt("fake-client-key-pem"),
    )
    db_session.add(cred)
    db_session.commit()
    db_session.refresh(cred)

    host = ClientHost(name="proxmox1", ssh_credential_id=cred.id, borgmatic_config_path="/etc/borgmatic/config.yaml")
    db_session.add(host)
    db_session.commit()
    db_session.refresh(host)
    return host


def test_trigger_backup_success(db_session, monkeypatch):
    host = _make_host(db_session)

    def fake_exec(hostname, port, username, key_pem, passphrase, command, timeout=None):
        assert hostname == "proxmox1.lan"
        assert "borgmatic" in command
        assert "/etc/borgmatic/config.yaml" in command
        assert "create" in command
        return 0, "Archive created successfully.", ""

    monkeypatch.setattr(ssh_exec, "exec_command", fake_exec)

    run = host_service.trigger_backup(db_session, host, repo_id=1)
    assert run.status == "success"
    assert "Archive created" in run.output_log


def test_trigger_backup_never_calls_prune(db_session, monkeypatch):
    """Retention is centrally owned by the portal -- the remote command must be
    `create` only, never a full borgmatic run that could also invoke `prune`."""
    host = _make_host(db_session)
    seen_commands = []

    def fake_exec(hostname, port, username, key_pem, passphrase, command, timeout=None):
        seen_commands.append(command)
        return 0, "", ""

    monkeypatch.setattr(ssh_exec, "exec_command", fake_exec)
    host_service.trigger_backup(db_session, host, repo_id=1)

    assert len(seen_commands) == 1
    assert "prune" not in seen_commands[0]


def test_trigger_backup_ssh_failure_recorded_as_failed_run(db_session, monkeypatch):
    host = _make_host(db_session)

    def fake_exec(hostname, port, username, key_pem, passphrase, command, timeout=None):
        raise ssh_exec.SSHExecError("Could not connect: connection timed out")

    monkeypatch.setattr(ssh_exec, "exec_command", fake_exec)

    run = host_service.trigger_backup(db_session, host, repo_id=1)
    assert run.status == "failed"
    assert "connection timed out" in run.output_log

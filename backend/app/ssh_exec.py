"""Executes a command on a client host over SSH, to remotely trigger a borgmatic run.

Separate from borg_runner.py: this is for reaching into a *client* machine
(which needs to read its own local filesystem to create an archive), whereas
repo monitoring/pruning talks directly to the repo via borg's own SSH
transport and never touches the client at all.
"""

import io

import paramiko

from app import config


class SSHExecError(RuntimeError):
    pass


def _load_private_key(pem: str, passphrase: str = None):
    key_classes = (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey, paramiko.DSSKey)
    last_exc = None
    for key_cls in key_classes:
        try:
            return key_cls.from_private_key(io.StringIO(pem), password=passphrase or None)
        except paramiko.SSHException as e:
            last_exc = e
    raise SSHExecError(f"Could not load private key (tried ed25519/ecdsa/rsa/dss): {last_exc}")


def exec_command(hostname: str, port: int, username: str, private_key_pem: str, key_passphrase: str, command: str, timeout: int = None):
    """Returns (exit_code, stdout, stderr). Raises SSHExecError if the connection itself fails."""
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # TOFU by default -- see docs/SECURITY.md for pre-pinning known_hosts on hardened setups.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    pkey = _load_private_key(private_key_pem, key_passphrase)

    try:
        client.connect(hostname, port=port, username=username, pkey=pkey, timeout=30)
    except (paramiko.SSHException, OSError) as e:
        raise SSHExecError(f"Could not connect to {username}@{hostname}:{port}: {e}") from e

    try:
        _, stdout, stderr = client.exec_command(command, timeout=timeout or config.COMMAND_TIMEOUT_SECONDS)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return exit_code, out, err
    finally:
        client.close()

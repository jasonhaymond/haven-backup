"""One-line client enrollment: token handling, key generation, and rendering every
file/line the client install script writes. All templating lives here (not in the
bash script) so it's covered by the test suite. See docs/CLIENT_ENROLLMENT.md.
"""

import base64
import hashlib
import json
import re
import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

CLIENT_CONFIG_PATH = "/etc/borgmatic/haven.yaml"
CLIENT_BORG_KEY_PATH = "/root/.ssh/haven_borg_ed25519"
SYSTEMD_UNIT_NAME = "haven-backup"

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:-]{0,252}$")
ABS_PATH_RE = re.compile(r"^/[A-Za-z0-9._/@+-]*$")
# Deliberately narrower than systemd's full OnCalendar grammar: this ends up in a
# unit file written as root, so no quotes, newlines, or anything shell-ish.
SCHEDULE_RE = re.compile(r"^[A-Za-z0-9 :*,/.~-]{1,64}$")
PUBKEY_TYPES = {"ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521"}


class EnrollmentError(ValueError):
    pass


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_passphrase() -> str:
    return secrets.token_urlsafe(32)


def generate_keypair(comment: str) -> tuple[str, str]:
    """Returns (private key in OpenSSH PEM format, public key line)."""
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()
    ).decode("ascii")
    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode("ascii")
    return private_pem, f"{public} {comment}"


def validate_name(name: str) -> str:
    if not NAME_RE.match(name):
        raise EnrollmentError("Name must be 1-64 characters: letters, digits, '.', '_' or '-', starting with a letter or digit")
    return name


def validate_abs_path(path: str, what: str) -> str:
    path = path.strip()
    if not ABS_PATH_RE.match(path) or "/../" in f"{path}/":
        raise EnrollmentError(f"{what} must be an absolute path (letters, digits, and ._/@+- only): {path!r}")
    return path.rstrip("/") or "/"


def validate_schedule(schedule: str) -> str:
    schedule = schedule.strip()
    if not SCHEDULE_RE.match(schedule):
        raise EnrollmentError("Schedule must be a systemd OnCalendar expression, e.g. '*-*-* 02:00:00' or 'daily'")
    return schedule


def validate_hostname(hostname: str) -> str:
    hostname = hostname.strip()
    if not HOSTNAME_RE.match(hostname):
        raise EnrollmentError(f"Invalid hostname/address: {hostname!r}")
    return hostname


def normalize_public_key(raw: str) -> str:
    """The client's public key ends up in an authorized_keys line the admin pastes on the
    backup server as root -- so anything beyond exactly `<type> <base64>` (a newline
    smuggling in a second, unrestricted key; extra options) must be rejected, not trimmed."""
    if any(c in raw for c in "\r\n\0\"") or len(raw) > 16384:
        raise EnrollmentError("Public key must be a single OpenSSH public key line")
    parts = raw.strip().split()
    if len(parts) < 2 or parts[0] not in PUBKEY_TYPES:
        raise EnrollmentError("Unsupported public key type")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (ValueError, base64.binascii.Error) as e:
        raise EnrollmentError("Public key is not valid base64") from e
    # The blob's own embedded type string must match the declared one.
    type_len = int.from_bytes(blob[:4], "big") if len(blob) >= 4 else -1
    if blob[4 : 4 + type_len].decode("ascii", errors="replace") != parts[0]:
        raise EnrollmentError("Public key type does not match its contents")
    return f"{parts[0]} {parts[1]}"


def repo_path(base_path: str, name: str) -> str:
    return f"{base_path.rstrip('/')}/{name}"


def repo_url(username: str, hostname: str, port: int, base_path: str, name: str) -> str:
    return f"ssh://{username}@{hostname}:{port}{repo_path(base_path, name)}"


def parse_version(text: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", text or "")
    return tuple(int(p) for p in match.group(0).split(".")) if match else (0,)


def _q(value: str) -> str:
    # A JSON string is a valid YAML double-quoted scalar, which avoids needing PyYAML.
    return json.dumps(value)


def render_borgmatic_config(borgmatic_version: str, name: str, url: str, passphrase: str, sources: list[str]) -> str:
    ssh_command = f"ssh -i {CLIENT_BORG_KEY_PATH} -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
    header = (
        f"# Written by Haven Backup enrollment for {name!s}. Retention is owned by the portal,\n"
        "# so this file deliberately has no keep_* settings and is only ever run with `create`.\n"
        "# See docs/CLIENT_ENROLLMENT.md before editing.\n"
    )
    source_lines = "".join(f"    - {_q(s)}\n" for s in sources)

    # borgmatic 1.8 flattened the config and deprecated the location:/storage: sections;
    # Debian 12 / Proxmox 8 still ship 1.7.x, which only understands the sectioned form.
    if parse_version(borgmatic_version) >= (1, 8):
        return (
            header
            + "source_directories:\n"
            + source_lines.replace("    - ", "  - ")
            + "repositories:\n"
            + f"  - path: {_q(url)}\n"
            + "    label: haven\n"
            + "exclude_caches: true\n"
            + f"encryption_passphrase: {_q(passphrase)}\n"
            + f"ssh_command: {_q(ssh_command)}\n"
        )
    return (
        header
        + "location:\n"
        + "  source_directories:\n"
        + source_lines
        + "  repositories:\n"
        + f"    - {_q(url)}\n"
        + "  exclude_caches: true\n"
        + "storage:\n"
        + f"  encryption_passphrase: {_q(passphrase)}\n"
        + f"  ssh_command: {_q(ssh_command)}\n"
    )


def backup_command(borgmatic_path: str) -> str:
    return f"{borgmatic_path} --config {CLIENT_CONFIG_PATH} create --stats"


def render_systemd_service(name: str, borgmatic_path: str) -> str:
    return (
        "[Unit]\n"
        f"Description=Haven Backup: borgmatic create ({name})\n"
        "Wants=network-online.target\n"
        "After=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={backup_command(borgmatic_path)}\n"
        "Nice=10\n"
        "IOSchedulingClass=idle\n"
    )


def render_systemd_timer(name: str, schedule: str) -> str:
    return (
        "[Unit]\n"
        f"Description=Haven Backup: scheduled borgmatic create ({name})\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar={schedule}\n"
        "RandomizedDelaySec=15m\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def portal_authorized_keys_line(portal_public_key: str, borgmatic_path: str) -> str:
    """Goes in the client's /root/.ssh/authorized_keys: the portal's key can only ever
    run this one command there, whatever it asks for."""
    return f'command="{backup_command(borgmatic_path)}",restrict {portal_public_key}'


def backup_server_authorized_keys_line(client_public_key: str, base_path: str, name: str, client_hostname: str) -> str:
    return (
        f'command="borg serve --restrict-to-repository {repo_path(base_path, name)}",restrict '
        f"{client_public_key} haven-client@{client_hostname}"
    )

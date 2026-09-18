"""App settings, all overridable via environment variables."""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("HAVEN_DATA_DIR", "./data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = Path(os.environ.get("HAVEN_DB_PATH", str(DATA_DIR / "haven.db")))
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

SECRET_KEY_FILE = Path(os.environ.get("HAVEN_SECRET_KEY_FILE", str(DATA_DIR / "secret.key")))

# Signs session cookies. Independent of SECRET_KEY_FILE (which encrypts stored
# SSH keys/passphrases) so rotating one doesn't invalidate the other.
SESSION_SECRET_FILE = Path(os.environ.get("HAVEN_SESSION_SECRET_FILE", str(DATA_DIR / "session.key")))
SESSION_COOKIE_NAME = "haven_session"
SESSION_MAX_AGE_SECONDS = int(os.environ.get("HAVEN_SESSION_MAX_AGE", str(60 * 60 * 24 * 14)))  # 14 days

# Secure requires HTTPS between the browser and whatever terminates TLS in front of
# this app -- true by default. Only disable for plain-http local dev (the Vite dev
# proxy on http://localhost), never in a real deployment.
COOKIE_SECURE = os.environ.get("HAVEN_COOKIE_SECURE", "true").lower() not in ("false", "0", "no")

LOGIN_RATE_LIMIT_ATTEMPTS = int(os.environ.get("HAVEN_LOGIN_RATE_LIMIT_ATTEMPTS", "10"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("HAVEN_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))

# Path to the ssh keys materialized on disk for `borg`'s BORG_RSH -- these are
# decrypted-on-demand copies, written with 0600 perms immediately before use.
SSH_KEY_WORKDIR = Path(os.environ.get("HAVEN_SSH_KEY_WORKDIR", str(DATA_DIR / "ssh_keys")))
SSH_KEY_WORKDIR.mkdir(parents=True, exist_ok=True)

BORG_BINARY = os.environ.get("HAVEN_BORG_BINARY", "borg")
BORGMATIC_BINARY = os.environ.get("HAVEN_BORGMATIC_BINARY", "borgmatic")
COMMAND_TIMEOUT_SECONDS = int(os.environ.get("HAVEN_COMMAND_TIMEOUT", "3600"))

STATUS_REFRESH_INTERVAL_MINUTES = int(os.environ.get("HAVEN_STATUS_REFRESH_MINUTES", "30"))
PRUNE_INTERVAL_HOURS = int(os.environ.get("HAVEN_PRUNE_INTERVAL_HOURS", "24"))
NOTIFICATION_WEBHOOK_URL = os.environ.get("HAVEN_NOTIFICATION_WEBHOOK_URL")

FRONTEND_ORIGIN = os.environ.get("HAVEN_FRONTEND_ORIGIN", "http://localhost:5173")

# Update-available check: an outbound call to GitHub's public tags API for this repo,
# no request body, no auth, nothing project-specific sent beyond "what tags exist" --
# but it's still an outbound call from a tool that holds SSH keys/passphrases, so it's
# opt-out rather than silently unconditional. Disable entirely with HAVEN_UPDATE_CHECK_ENABLED=false.
UPDATE_CHECK_ENABLED = os.environ.get("HAVEN_UPDATE_CHECK_ENABLED", "true").lower() not in ("false", "0", "no")
UPDATE_CHECK_REPO = os.environ.get("HAVEN_UPDATE_CHECK_REPO", "jasonhaymond/haven-backup")

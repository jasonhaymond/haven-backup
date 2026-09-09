# Deployment

## Docker Compose (recommended)

```bash
git clone https://github.com/jasonhaymond/haven-backup.git
cd haven-backup
docker compose up -d --build
```

This starts two containers:
- `backend` -- FastAPI + the portal's SQLite DB, on an internal port only
  (borg + borgmatic + openssh-client are installed in its image).
- `web` -- the built React app served by Caddy, which also reverse-proxies
  `/api/*` to `backend` -- so the browser only ever talks to one origin
  (`web`), avoiding CORS/cookie cross-origin concerns entirely.

Open `http://<host>:8080` and create the first admin account.

Portal data (SQLite DB, encryption key, materialized SSH keys) lives in the
`haven_data` named volume -- back this up like you would an SSH `known_hosts`
+ private key directory (see [SECURITY.md](SECURITY.md)).

### Put it behind your own reverse proxy / TLS

`web`'s container listens on plain HTTP inside the Compose network. Put your
existing reverse proxy (Caddy, nginx, Traefik) in front of the `8080` port
for TLS -- don't expose it directly to the internet without one.

### Configuration via environment variables

Set these on the `backend` service in `docker-compose.yml`:

| Variable | Default | Purpose |
|---|---|---|
| `HAVEN_STATUS_REFRESH_MINUTES` | `30` | How often every repo's status is refreshed |
| `HAVEN_PRUNE_INTERVAL_HOURS` | `24` | How often scheduled retention pruning runs |
| `HAVEN_NOTIFICATION_WEBHOOK_URL` | unset | Generic webhook (ntfy/Discord/Slack adapter URL) for health-transition/prune-failure alerts |
| `HAVEN_COMMAND_TIMEOUT` | `3600` | Max seconds for a single borg/borgmatic/ssh command |
| `HAVEN_SESSION_MAX_AGE` | 14 days (seconds) | How long a login session lasts |

## Bare-metal / systemd (without Docker)

You'll need `borg`, `borgmatic`, and `openssh-client` installed on the portal
host itself (not the clients -- the clients already have these if they run
borgmatic). Then:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
HAVEN_DATA_DIR=/var/lib/haven-backup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Build the frontend separately and serve it (with your own reverse proxy
config to send `/api/*` to `127.0.0.1:8000`):

```bash
cd frontend
npm ci
npm run build   # outputs frontend/dist -- serve with nginx/Caddy, proxy /api to the backend
```

A systemd unit for the backend:

```ini
# /etc/systemd/system/haven-backup-portal.service
[Unit]
Description=Haven Backup Portal
After=network-online.target

[Service]
User=haven-portal
Environment=HAVEN_DATA_DIR=/var/lib/haven-backup
WorkingDirectory=/opt/haven-backup/backend
ExecStart=/opt/haven-backup/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## First run

1. Open the portal, create the first admin account (only available while no
   users exist -- see `POST /api/auth/setup`).
2. Add an **SSH credential** for reaching your Borg backup host.
3. Add a **repository**: its `ssh://` URL, that credential, its Borg
   passphrase, and a retention policy.
4. Click **Refresh now** on the repo to confirm the portal can actually reach
   it -- see [BORG_COMPATIBILITY.md](BORG_COMPATIBILITY.md) if the numbers
   don't look right.
5. Optionally add a **client host** (+ its own SSH credential) if you want
   the "backup now" button -- see [BORGMATIC_INTEGRATION.md](BORGMATIC_INTEGRATION.md)
   first for how retention ownership should be split.

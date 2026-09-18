# Deployment

Two ways to stand up the Docker Compose deployment (recommended) -- an
automated setup script, or the full manual walkthrough. Both end in the same
place: a running stack, configured the same way. A bare-metal/systemd path
without Docker is also documented below for when that's a better fit.

## Docker Compose -- Option A: automated setup script

```bash
git clone https://github.com/jasonhaymond/haven-backup.git
cd haven-backup
./scripts/setup.sh
```

This checks that Docker + the Compose plugin are installed, warns if the
port you choose already has something listening on it, prompts for each
setting in [.env.example](../.env.example) (offering your existing `.env`'s
values as defaults if you re-run it), writes `.env`, and offers to run
`docker compose up -d --build` for you. It only ever touches files inside
this project directory (`.env`, the Compose stack) -- it deliberately does
**not** touch firewall rules or your reverse proxy, since those are shared
system state it doesn't own. See "Put it behind your own reverse proxy"
below for that part, which stays a manual step regardless of which option
you use here.

Safe to re-run any time you want to change a setting.

## Docker Compose -- Option B: manual walkthrough

Same end state as Option A, step by step:

```bash
git clone https://github.com/jasonhaymond/haven-backup.git
cd haven-backup
```

1. **Check prerequisites**: `docker --version` and `docker compose version`
   both need to succeed. If not, install Docker Engine + the Compose plugin:
   https://docs.docker.com/engine/install/
2. **Check the port is free**: by default the web UI publishes on `8080`.
   `lsof -iTCP:8080 -sTCP:LISTEN` (or `ss -ltnp | grep 8080`) should print
   nothing. If something's already there, you'll override `WEB_PORT` in the
   next step.
3. **Create your config**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` in a text editor -- every variable is documented inline.
   `WEB_PORT` is the one you're most likely to change; everything else has a
   working default.
4. **Build and start**:
   ```bash
   docker compose up -d --build
   ```
5. **Verify it's up**:
   ```bash
   curl http://localhost:8080/api/health
   # {"status":"ok","version":"0.2.0","database":true}
   ```

This starts two containers:
- `backend` -- FastAPI + the portal's SQLite DB, reachable only from inside
  the Compose network (borg + borgmatic + openssh-client are installed in
  its image).
- `web` -- the built React app served by Caddy, which also reverse-proxies
  `/api/*` to `backend` -- so the browser only ever talks to one origin
  (`web`), avoiding CORS/cookie cross-origin concerns entirely.

Log output for either container: `docker compose logs -f backend` (or `web`).
Both containers cap their own logs at 10MB x 3 files (see `docker-compose.yml`'s
`logging:` blocks) so they can't silently fill the host's disk.

Portal data (SQLite DB, encryption key, materialized SSH keys) lives in the
`haven_data` named volume -- see [BACKUP.md](BACKUP.md) for backing this up,
and [SECURITY.md](SECURITY.md) for what it protects and doesn't.

### Put it behind your own reverse proxy / TLS

`web`'s container listens on plain HTTP inside the Compose network -- that's
why `.env.example` defaults `HAVEN_COOKIE_SECURE=false` (a real browser
refuses to even store a cookie marked `Secure` over plain HTTP, which would
otherwise silently break login). This is a manual step regardless of which
option above you used, since it touches your reverse proxy/firewall, not
just this project's own files:

1. Put your existing reverse proxy (Caddy, nginx, Traefik) in front of the
   `WEB_PORT` you chose, terminating TLS there. Don't expose that port
   directly to the internet without one.
2. Once real TLS is in front, set `HAVEN_COOKIE_SECURE=true` in `.env` and
   run `docker compose up -d` again to pick it up.
3. Firewall: only ports `80`/`443` (your reverse proxy) and `22` (SSH) need
   to be reachable from outside this machine -- `WEB_PORT` itself shouldn't
   need to be, once the proxy is in front of it.

### Configuration reference

Every variable, with its default, is documented in
[.env.example](../.env.example) -- that file is the source of truth, kept in
sync with `backend/app/config.py`.

## Bare-metal / systemd (without Docker)

You'll need `borg`, `borgmatic`, and `openssh-client` installed on the portal
host itself (not the clients -- the clients already have these if they run
borgmatic). Same prerequisite/port checks as above apply, just against your
own host instead of a container:

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
# Terminating TLS at your reverse proxy in front of this host? Also set:
# Environment=HAVEN_COOKIE_SECURE=true
WorkingDirectory=/opt/haven-backup/backend
ExecStart=/opt/haven-backup/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Updating an existing bare-metal install: `git pull`, re-run
`.venv/bin/pip install -e .` (in case dependencies changed),
`npm ci && npm run build` for the frontend, then
`systemctl restart haven-backup-portal`. There's no automated update script
for this path yet -- see "Updating" below.

## First run

1. Open the portal, create the first admin account (only available while no
   users exist -- see `POST /api/auth/setup`). Add more admins later with
   `backend/scripts/create_user.py`.
2. Add an **SSH credential** for reaching your Borg backup host.
3. Add a **repository**: its `ssh://` URL, that credential, its Borg
   passphrase, and a retention policy.
4. Click **Refresh now** on the repo to confirm the portal can actually reach
   it -- see [BORG_COMPATIBILITY.md](BORG_COMPATIBILITY.md) if the numbers
   don't look right.
5. Optionally add a **client host** (+ its own SSH credential) if you want
   the "backup now" button -- see [BORGMATIC_INTEGRATION.md](BORGMATIC_INTEGRATION.md)
   first for how retention ownership should be split.

## Updating (and rolling back)

```bash
./scripts/update.sh          # deploy the latest commit
./scripts/update.sh v0.2.0   # deploy/roll back to that exact tagged version
```

This refuses to run if there are uncommitted local changes, takes its own
pre-restart snapshot of the portal's own data (independent of whatever
backup schedule you've set up separately -- into `backups/`), rebuilds and
restarts both containers, then polls `/api/health` until it responds before
declaring success.

**Rolling back only ever rolls back code.** If the tag you're targeting
expects a different database schema/state than what's currently running,
restoring the database to match it is a **separate, manual, deliberate**
step -- see [BACKUP.md](BACKUP.md#restoring). The script will never do that
part for you implicitly; restoring a snapshot discards everything written
since it was taken.

Every shipped version is tagged in git (`v0.2.0`, etc.) -- `git tag --list
'v*'` to see what's available to target.

Prefer the manual equivalent? `git fetch --tags && git checkout <tag-or-branch>
&& docker compose up -d --build`, then take your own snapshot per
[BACKUP.md](BACKUP.md) first if you're rolling back rather than forward.
There's no in-app "check for updates" button yet -- this is an SSH/terminal
step for now.

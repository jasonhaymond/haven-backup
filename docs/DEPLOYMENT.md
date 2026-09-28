# Deployment

[← Back to README](../README.md) · [Architecture](ARCHITECTURE.md) ·
[Borgmatic integration](BORGMATIC_INTEGRATION.md) ·
[Restricted SSH accounts](RESTRICTED_SSH_ACCOUNTS.md) ·
[Borg compatibility](BORG_COMPATIBILITY.md) · [Security](SECURITY.md) ·
[Backup](BACKUP.md) ·
[Client enrollment](CLIENT_ENROLLMENT.md)

## Contents
- [One-line install](#one-line-install)
- [Docker Compose -- Option A: automated setup script](#option-a-setup-script)
- [Docker Compose -- Option B: manual walkthrough](#option-b-manual)
  - [Put it behind your own reverse proxy / TLS](#reverse-proxy-tls)
  - [Configuration reference](#configuration-reference)
- [Bare-metal / systemd (without Docker)](#bare-metal-systemd)
- [First run](#first-run)
- [Updating (and rolling back)](#updating-and-rolling-back)

Two ways to stand up the Docker Compose deployment (recommended) -- an
automated setup script, or the full manual walkthrough. Both end in the same
place: a running stack, configured the same way. A bare-metal/systemd path
without Docker is also documented below for when that's a better fit.

<a id="one-line-install"></a>
## One-line install

On a fresh host that already has Docker (with the Compose plugin) and git, as a user
that can run `docker` without sudo:

```bash
curl -fsSL https://raw.githubusercontent.com/jasonhaymond/haven-backup/master/scripts/install.sh | bash
```

This is Option A below with the clone done for you. It checks for git, Docker, the
Compose plugin and Docker access, clones the repo into `~/haven-backup`, and runs
`scripts/setup.sh` interactively. Options go after `-s --`:

```bash
curl -fsSL .../scripts/install.sh | bash -s -- --dir /opt/haven-backup --version v1.0.0
```

- `--dir <path>`: where to clone (default `~/haven-backup`).
- `--version <tag>`: check out that tagged release instead of the latest `master`.
  `scripts/update.sh <tag>` moves between versions afterwards.

Like `setup.sh`, it never installs system packages or touches the firewall or reverse
proxy. If Docker or git is missing it stops and says so. If the folder already holds a
Haven Backup checkout, it prints the update command instead of cloning again.

**What success looks like:** `[ok] git, Docker and Docker Compose found`, then
`[ok] Checked out <version>`, then `setup.sh`'s prompts (see Option A below).

Once the portal is running, add machines to back up with
[client enrollment](CLIENT_ENROLLMENT.md).

<a id="option-a-setup-script"></a>
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

**What success looks like:** if you let it start the stack, the script ends
by printing `Started. Open http://localhost:<port> to create the first
admin account.` The script itself doesn't poll a health check, so confirm
it separately -- run `curl http://localhost:<port>/api/health` and expect
the same `{"status":"ok",...}` response shown in step 5 of Option B below.
If that doesn't come back, check `docker compose logs -f backend` (or
`web`) before continuing.

Safe to re-run any time you want to change a setting.

<a id="option-b-manual"></a>
## Docker Compose -- Option B: manual walkthrough

Same end state as Option A, step by step:

```bash
git clone https://github.com/jasonhaymond/haven-backup.git
cd haven-backup
```

1. **Check prerequisites**: `docker --version` and `docker compose version`
   both need to succeed. If not, install Docker Engine + the Compose plugin:
   https://docs.docker.com/engine/install/
   **Success looks like:** each command prints a version number (e.g.
   `Docker version 27.x...` and `Docker Compose version v2.x...`), not
   "command not found."
2. **Check the port is free**: by default the web UI publishes on `8080`.
   `lsof -iTCP:8080 -sTCP:LISTEN` (or `ss -ltnp | grep 8080`) should print
   nothing. If something's already there, you'll override `WEB_PORT` in the
   next step.
   **Success looks like:** no output at all from that command -- any output
   means something's already bound to the port.
3. **Create your config**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` in a text editor -- every variable is documented inline.
   `WEB_PORT` is the one you're most likely to change; everything else has a
   working default.
   **Success looks like:** `cat .env` shows your edited values, and the file
   still parses as `KEY=value` lines (no stray quotes/line breaks from your
   editor).
4. **Build and start**:
   ```bash
   docker compose up -d --build
   ```
   **Success looks like:** the command ends with two lines like
   `Container haven-backup-backend-1  Started` and
   `Container haven-backup-web-1  Started` (not `Exited`), and
   `docker compose ps` shows both with a status of `running`/`Up`.
5. **Verify it's up**:
   ```bash
   curl http://localhost:8080/api/health
   # {"status":"ok","version":"<current version>","database":true}
   ```
   **Success looks like:** exactly that JSON shape, with `"status":"ok"` and
   `"database":true`. `version` will show whatever's actually running, not
   literally `<current version>` -- see [CHANGELOG.md](../CHANGELOG.md) for
   what that number should be as of your checkout.

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

<a id="reverse-proxy-tls"></a>
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

**What success looks like:** `curl https://yourdomain.com/api/health`
(through the real proxy/domain, not `localhost`) returns the same
`{"status":"ok",...}` JSON as step 5 above, and logging in through the
browser persists a session (reloading the page after login doesn't bounce
you back to the login screen). If login silently fails to "stick" after
enabling `HAVEN_COOKIE_SECURE=true`, that almost always means the proxy
isn't actually serving HTTPS yet for that request -- see
[SECURITY.md](SECURITY.md#login) for why.

<a id="configuration-reference"></a>
### Configuration reference

Every variable, with its default, is documented in
[.env.example](../.env.example) -- that file is the source of truth, kept in
sync with `backend/app/config.py`.

<a id="bare-metal-systemd"></a>
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

**Success looks like:** uvicorn logs `Application startup complete.` and
`curl http://127.0.0.1:8000/api/health` (from the same host) returns
`{"status":"ok","database":true,...}`.

Build the frontend separately and serve it (with your own reverse proxy
config to send `/api/*` to `127.0.0.1:8000`):

```bash
cd frontend
npm ci
npm run build   # outputs frontend/dist -- serve with nginx/Caddy, proxy /api to the backend
```

**Success looks like:** `npm run build` ends with a `vite v... building
client environment for production...` block and `✓ built in <N>ms`, and
`frontend/dist/index.html` exists.

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

**Success looks like:** `systemctl status haven-backup-portal` reports
`active (running)`, and `journalctl -u haven-backup-portal -n 20` shows
`Application startup complete.` with no traceback after it.

<a id="first-run"></a>
## First run

1. Open the portal, create the first admin account (only available while no
   users exist -- see `POST /api/auth/setup`). Add more admins later with
   `backend/scripts/create_user.py`; locked out of an existing one, use
   `backend/scripts/reset_password.py` -- see [SECURITY.md](SECURITY.md).
   **Success looks like:** submitting the form logs you straight into the
   dashboard -- no separate "check your email" or confirmation step exists.
2. Add an **SSH credential** for reaching your Borg backup host. If that
   host already gives other apps their own locked-down account instead of
   a shared full-shell one, see
   [RESTRICTED_SSH_ACCOUNTS.md](RESTRICTED_SSH_ACCOUNTS.md) before creating
   Haven Backup's -- it should get the same treatment, not an exception.
   **Success looks like:** the credential appears in the SSH Credentials
   list with no error banner after saving.
3. Add a **repository**: its `ssh://` URL, that credential, its Borg
   passphrase, and a retention policy.
4. Click **Refresh now** on the repo to confirm the portal can actually reach
   it -- see [BORG_COMPATIBILITY.md](BORG_COMPATIBILITY.md) if the numbers
   don't look right.
   **Success looks like:** the repo's status badge turns healthy and shows a
   real archive count/size instead of an error message. An error here means
   the SSH credential, repo URL, or passphrase (or a restricted account's
   `--restrict-to-path`) doesn't line up -- fix that before moving on rather
   than adding a client host against a repo that isn't reachable yet.
5. Add machines to back up. For a new Debian/Ubuntu/Proxmox machine, use
   **Client Hosts → Enroll a new host** ([CLIENT_ENROLLMENT.md](CLIENT_ENROLLMENT.md)):
   one command on the machine sets up borgmatic, a timer, the repo and the
   "backup now" access, and registers them here. For a machine where
   borgmatic is already set up by hand, optionally add a **client host**
   (+ its own SSH credential) if you want the "backup now" button -- see [BORGMATIC_INTEGRATION.md](BORGMATIC_INTEGRATION.md)
   first for how retention ownership should be split.
   **Success looks like:** clicking "Backup now" shows a run starting, and
   it finishes with a status of success on the host's run history rather
   than an SSH/auth error.

<a id="updating-and-rolling-back"></a>
## Updating (and rolling back)

```bash
./scripts/update.sh          # deploy the latest commit
./scripts/update.sh v0.2.0   # deploy/roll back to that exact tagged version
```

This refuses to run if there are uncommitted local changes, takes its own
pre-restart snapshot of the portal's own data -- labeled by the version
actually stamped in the database at that moment, not the git tree (see
[BACKUP.md](BACKUP.md)), independent of whatever backup schedule you've set
up separately -- into `backups/`, rebuilds and restarts both containers,
then polls `/api/health` until it responds before declaring success.

**What success looks like:** the script's last two lines are
`Healthy: {"status":"ok","version":"<the version you targeted>",...}`
followed by `Update complete.` If it instead exits with an error before
that, nothing was left half-applied that requires manual cleanup -- the
snapshot was already taken, so re-run once you've fixed whatever it flagged
(uncommitted changes, a build failure, etc.).

The UI's sidebar shows whether a newer tagged release exists (an outbound
check against GitHub -- see [SECURITY.md](SECURITY.md#update-available-check-outbound-call-to-github)
for the kill switch), so you don't have to go looking for this manually --
but it's visibility only. Nothing in the UI can trigger the actual update;
`./scripts/update.sh` above (or its manual equivalent) is still how it
actually happens.

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
The UI can tell you an update exists; actually running one is still an
SSH/terminal step, deliberately -- see [SECURITY.md](SECURITY.md#update-available-check-outbound-call-to-github)
for why.

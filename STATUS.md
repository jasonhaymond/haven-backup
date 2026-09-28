# HavenBackup — Status

_Last updated: 2026-09-28, at v1.0.0 (first written 2026-09-11). Written so a brand-new Claude session can pick this up cold._

## 1. Project overview

Haven Backup is a **web portal that configures and monitors existing Borg
backups** — it is a control-plane/UI layer, not a backup engine itself. It
sits in front of Borg repos and `borgmatic` clients already running on the
owner's infrastructure (Proxmox, Nextcloud, etc.) and gives one place to:

- see a dashboard of every repo (last archive time, size, dedup stats,
  health/staleness badge),
- set and enforce a centralized retention policy (`borg prune`, scheduled or
  on-demand, dry-run first),
- trigger a real `borgmatic create` run on a client host from the UI
  ("backup now"),
- run `borg check` and view full run history/logs for every backup, prune,
  and check.

Relative to the owner's other projects: this is the intended general
whole-server/infrastructure backup tool referenced from his global cross-project
standards doc, **not** a per-app database backup mechanism (those stay
app-specific, e.g. Haydrop's own `/admin/backups`). Haven Backup's job is to be
the monitoring/retention/trigger front-end for Borg-based backups across
whatever infrastructure the owner runs — Proxmox, Nextcloud, and future
hosts — from one dashboard.

**Important framing change from the name:** despite the name suggesting a
backup *tool*, the current (and intended long-term) design does **not**
implement its own storage/encryption/dedup engine. It deliberately defers all
of that to Borg, which already does it well. See section 3 for why this
matters when reading the repo.

## 2. Tech stack & architecture

- **Backend**: Python, FastAPI + SQLModel over SQLite. Runs `borg`/`borgmatic`
  as local subprocesses and reaches client hosts via `paramiko` SSH.
- **Frontend**: React + Vite + Tailwind SPA, talking to the backend's JSON
  API. Built and served by Caddy in the Docker image (also reverse-proxies
  `/api/*` to the backend so the browser only ever talks to one origin).
- Login is built in: bcrypt password hashing + signed (`itsdangerous`),
  httpOnly session cookies. No JWT library, no external session store, no
  rate limiting or 2FA (see `docs/SECURITY.md`).

### Two distinct remote-access paths (by design, see `docs/ARCHITECTURE.md`)

1. **Repo monitoring & retention** (`borg info`/`list`/`prune`/`check`) run
   as local subprocesses *inside the portal's own container/host*, pointed at
   a repo's `ssh://` URL — Borg opens its own SSH connection via `BORG_RSH`
   (same mechanism `git` uses for `git+ssh`). The portal never needs SSH
   access to a *client* machine for this, only to the backup host holding the
   repo.
2. **"Backup now"** is the one place the portal reaches into a *client*
   machine, over SSH via `paramiko`, to run `borgmatic ... create` there
   (it has to run locally on the client to read the client's filesystem).
   Deliberately `create`-only — never a client's full borgmatic action list —
   so the portal stays the sole owner of retention/`prune` and doesn't fight
   each client's own borgmatic config (see `docs/BORGMATIC_INTEGRATION.md`
   for the recommended client-side config split).

### Backend module map (`backend/app/`)

- `main.py` — FastAPI app, CORS, lifespan (DB init + scheduler start/stop)
- `models.py` — SQLModel tables: users, SSH credentials, client hosts, repos,
  run history
- `borg_runner.py` — builds/runs `borg` commands locally (`BORG_RSH` over
  `ssh://`), parses `borg info`/`list`/`prune` output. Verified against real
  Borg 1.2/1.4 repos at v1.0.0 (see section 3); other Borg versions, 2.x in
  particular, are still unverified.
- `ssh_exec.py` — `paramiko`-based SSH exec into a client host to trigger
  `borgmatic`
- `repo_service.py` — glues Repo model to `borg_runner` (refresh status,
  prune, check)
- `host_service.py` — glues ClientHost model to `ssh_exec` (trigger a backup
  run; builds the `borgmatic --config <path> create --stats` command)
- `enrollment.py` — one-line client enrollment: token generation/hashing,
  ed25519 keypairs, input validation (incl. rejecting smuggled SSH keys), and
  rendering every file the client script writes (borgmatic config in both
  pre-1.8 sectioned and 1.8+ flat formats, systemd units, both
  `authorized_keys` lines)
- `static/client-install.sh` — the client install script, served
  unauthenticated at `/api/enroll/install.sh`
- `rate_limit.py`, `version_stamp.py`, `notifications.py` — login/claim rate
  limiting, app-version stamping into the DB on boot, webhook notifications
- `scheduler.py` — in-process APScheduler: periodic status refresh + fires
  webhook on health transitions, scheduled pruning on a fixed interval
- `crypto.py` — AES-256-GCM encryption of SSH keys/passphrases at rest, using
  a key file generated on first run (`backend/data/secret.key` by default)
- `security.py` — password hashing (bcrypt), signed session cookies
- `config.py` — all settings, overridable via `HAVEN_*` env vars (data dir,
  DB path, key file paths, binary paths, timeouts, refresh/prune intervals,
  webhook URL, frontend origin)
- `routers/` — JSON API: `auth`, `credentials`, `hosts`, `repos`, `runs`,
  `dashboard`, `version`, `enrollments` (admin CRUD at `/api/enrollments`,
  plus the unauthenticated `/api/enroll/install.sh` and rate-limited
  `/api/enroll/claim`)

### Frontend module map (`frontend/src/`)

- `pages/` — Dashboard, Repositories, Repo detail, Client Hosts, Credentials,
  Login/Setup, Help
- `context/AuthContext.jsx` — auth state
- `lib/` — `api.js` (fetch client), `format.js`, `usePollRun.js` (run-status
  polling)
- `components/` — `Layout.jsx` (stacks on narrow screens), `RunStatusModal.jsx`,
  `ui.jsx`, `HelpBox.jsx` (per-page help), `EnrollHost.jsx` (enrollment form,
  one-time command display, enrollments list)

### Data stored by the portal itself

A small SQLite DB (`backend/app/models.py`): SSH credentials (private keys
encrypted at rest), client hosts, repos (Borg passphrases encrypted at rest),
enrollments (token hash only; pending passphrase and portal key encrypted),
run history for backups/prunes/checks, and the `AppMeta` version stamp. Lives in `backend/data/` (or the
`haven_data` Docker named volume). Treat this directory as a master key to
the whole backup estate — see `docs/SECURITY.md` for exactly what the AES-256-GCM
encryption-at-rest does and doesn't protect against (it does not protect
against anyone with access to a *running* instance's data dir + key file
together).


## 3. Current status

**v1.0.0, released 2026-09-28** (tagged and pushed; CI green on Python 3.10,
3.12 and the frontend build). Every version from v0.1.0 on is tagged.

What exists and has been verified:
- Full portal: auth/setup, SSH credentials, client hosts + "Backup now",
  repos + refresh/prune/check, run history, dashboard, update-available
  badge, per-page help, password reset/create-user scripts, version stamped
  into the DB on every boot.
- **One-line client enrollment** (v1.0.0): Client Hosts → Enroll a new host
  gives a single-use, expiring `curl … | sudo bash` command for
  Debian/Ubuntu/Proxmox. The script installs borg + borgmatic, writes
  `/etc/borgmatic/haven.yaml` + a systemd timer, registers host/repo/
  credential, and gives the portal a forced-command key that can only run
  `borgmatic create`. The one manual step is pasting the client's key line
  on the backup server (deliberate, per the root/shared-config risk tier);
  then the script runs `borg init` and the first backup. Guide:
  `docs/CLIENT_ENROLLMENT.md`.
- **One-line portal installer**: `scripts/install.sh` (clone + `setup.sh`).
- 82 backend tests (`backend/tests/`), plus `frontend/scripts/smoke.mjs`
  (Playwright).

**Verified end to end against real Borg (2026-09-28)**, in Docker: the
portal built from the tree (borg 1.4.0), a backup server (borg 1.2.4, sshd,
restricted account), and real systemd clients on Debian 12 (borg 1.2.4,
borgmatic 1.7.7, sectioned config) and Ubuntu 24.04 (borg 1.2.8, borgmatic
1.8.3, flat config). Enrollment, the scheduled first backup, "Backup now",
refresh, prune (dry and real), and check all worked, and both key
restrictions held (the portal key only runs the backup; the client key only
reaches its own repo). This found and fixed four bugs that would have hit
any fresh build: paramiko 4+ removing `DSSKey` (broke "Backup now" and left
runs stuck on "running"), sqlmodel rejecting naive archive datetimes (broke
refresh), the dashboard showing borg's chunk count as the archive count, and
the layout not working on phones.

Still not verified:
- Against the owner's **actual** Proxmox/Nextcloud hosts and backup server.
  No production deployment is recorded in this repo yet.
- Borg 2.x (command syntax and repo format differ; expect changes in
  `borg_runner.py`).
- Non-apt Linux clients (the manual walkthrough in `CLIENT_ENROLLMENT.md`
  covers them, but untested) and Windows (not supported, see section 6).

Main dependencies are unpinned (`requirements.txt` uses `>=`), so each
fresh Docker build pulls the latest paramiko/sqlmodel/etc. That's how the
bugs above got in unnoticed; CI catches API breaks only where tests cover
them.

## 4. Old prototype directories

`_old_agent_deprecated/`, root `haven_backup/` and root `tests/` (leftovers
from the two designs before the Borg-portal pivot, commit `8803576`) have
been deleted from disk. They were never tracked in git. `backend/`,
`frontend/`, `scripts/` and `docs/` are the whole current project.

## 5. Deployment

Docker Compose is primary: `backend` (FastAPI + borg + borgmatic +
openssh-client) and `web` (Caddy serving the SPA and proxying `/api/*`,
published on `WEB_PORT`, default 8080). Three ways to get there, all
ending in the same state:
- `curl -fsSL https://raw.githubusercontent.com/jasonhaymond/haven-backup/master/scripts/install.sh | bash`
  (optionally `-s -- --version v1.0.0 --dir <path>`),
- `git clone` + `./scripts/setup.sh`,
- the manual walkthrough in `docs/DEPLOYMENT.md` (also covers bare-metal/systemd).

Updates/rollbacks: `./scripts/update.sh [tag]`. It snapshots the portal's
data labeled with the DB-stamped version and health-checks after the
restart. Code rollback only; DB rollback is manual per `docs/BACKUP.md`.

Put it behind a TLS reverse proxy (Caddy by convention) before exposing it,
and set `HAVEN_COOKIE_SECURE=true` then. Enrollment also expects an https
portal URL: the client script refuses plain http unless given `--allow-http`.

The GitHub repo description is still the old generation-2 wording
("Encrypted, deduplicated backups … over local disk or SFTP"). It's worth
updating on GitHub; it's not in the repo itself.

## 6. Known issues / open work

- **First real deployment** against the owner's infrastructure, then enroll
  a real Proxmox and Nextcloud host (`docs/CLIENT_ENROLLMENT.md`).
- **Windows clients**: deliberately deferred. Borg/borgmatic don't run
  natively on Windows. Options (WSL2, WSL2 + VSS, a Windows-native tool)
  are in `docs/WINDOWS_CLIENTS.md`; needs a real Windows machine to decide.
- Consider pinning backend dependency versions (see section 3).
- No database migration tool: new tables appear via `create_all`, but
  changing an existing column needs manual handling (`docs/BACKUP.md`).
- Update-available is visible in the UI, but triggering the update from the
  UI isn't built (deliberately; `docs/SECURITY.md` explains why).
- No 2FA; SSH host-key verification is trust-on-first-use for both repo and
  client access (`docs/SECURITY.md` has the hardening steps).
- CI warnings: actions target the deprecated Node 20, and `ubuntu-latest`
  moves to Ubuntu 26 on 2026-10-19.

## 7. Recent history

- 2026-09-09: pivot to the Borg control-plane portal (`8803576`).
- 2026-09-17 to 09-22 (v0.2.0 to v0.5.3): brought in line with the global
  dev standards (setup/update scripts, DB version stamping, backups,
  health endpoint, update check), password reset script, per-page help,
  restricted-account docs, doc TOCs.
- 2026-09-28 (v1.0.0, `ee1263f`): client enrollment, portal installer, the
  four bug fixes found by the first live Borg test, responsive layout.

`git log --oneline` has the full list; `CHANGELOG.md` has the detail.

## 8. Pointers

- `README.md` — pitch, quick start, file layout, honest Status section
- `docs/CLIENT_ENROLLMENT.md` — adding a machine: one-line command, manual
  equivalent, troubleshooting, security model
- `docs/DEPLOYMENT.md` — installing/updating the portal, env vars
- `docs/ARCHITECTURE.md` — the two remote-access paths, why retention is
  centralized
- `docs/BORGMATIC_INTEGRATION.md` — keeping client borgmatic configs from
  fighting the portal's prune
- `docs/BORG_COMPATIBILITY.md` — what was verified and how to check another
  Borg version
- `docs/RESTRICTED_SSH_ACCOUNTS.md` — locked-down backup-server accounts
- `docs/SECURITY.md`, `docs/BACKUP.md`, `docs/WINDOWS_CLIENTS.md`
- Tests: `cd backend && pytest -q tests` (needs Python 3.10+; the owner's
  Windows box has 3.14 without pytest, so this session ran them in a
  `python:3.12-slim` container). CI: `.github/workflows/ci.yml`.

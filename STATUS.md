# HavenBackup — Status

_Last updated: 2026-09-11, by a research pass with no prior session memory of this project. Written so a brand-new Claude session can pick this up cold._

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
  `ssh://`), parses `borg info`/`list`/`prune` output. **This parsing is the
  single biggest unverified area of the whole project** — see section 6.
- `ssh_exec.py` — `paramiko`-based SSH exec into a client host to trigger
  `borgmatic`
- `repo_service.py` — glues Repo model to `borg_runner` (refresh status,
  prune, check)
- `host_service.py` — glues ClientHost model to `ssh_exec` (trigger a backup
  run; builds the `borgmatic --config <path> create --stats` command)
- `scheduler.py` — in-process APScheduler: periodic status refresh + fires
  webhook on health transitions, scheduled pruning on a fixed interval
- `crypto.py` — AES-256-GCM encryption of SSH keys/passphrases at rest, using
  a key file generated on first run (`backend/data/secret.key` by default)
- `security.py` — password hashing (bcrypt), signed session cookies
- `config.py` — all settings, overridable via `HAVEN_*` env vars (data dir,
  DB path, key file paths, binary paths, timeouts, refresh/prune intervals,
  webhook URL, frontend origin)
- `routers/` — JSON API: `auth`, `credentials`, `hosts`, `repos`, `runs`,
  `dashboard`

### Frontend module map (`frontend/src/`)

- `pages/` — Dashboard, Repositories, Repo detail, Client Hosts, Credentials,
  Login/Setup
- `context/AuthContext.jsx` — auth state
- `lib/` — `api.js` (fetch client), `format.js`, `usePollRun.js` (run-status
  polling)
- `components/` — `Layout.jsx`, `RunStatusModal.jsx`, `ui.jsx`

### Data stored by the portal itself

A small SQLite DB (`backend/app/models.py`): SSH credentials (private keys
encrypted at rest), client hosts, repos (Borg passphrases encrypted at rest),
and run history for backups/prunes/checks. Lives in `backend/data/` (or the
`haven_data` Docker named volume). Treat this directory as a master key to
the whole backup estate — see `docs/SECURITY.md` for exactly what the AES-256-GCM
encryption-at-rest does and doesn't protect against (it does not protect
against anyone with access to a *running* instance's data dir + key file
together).

## 3. Current status

**This is a young, single-session rebuild — treat it as functional-looking
but unverified against real infrastructure.**

What's implemented (code exists, has unit test coverage):
- Full backend API surface: auth/setup, SSH credentials CRUD, client hosts
  CRUD + backup-now trigger, repos CRUD + refresh/prune/check, run history,
  dashboard aggregation.
- AES-256-GCM crypto for secrets at rest, bcrypt + signed-cookie auth.
- APScheduler background jobs (status refresh, scheduled prune, webhook
  notification on health transitions).
- Full React frontend covering the same surface (dashboard, repo detail with
  retention controls and prune/check/run history, client hosts, credentials,
  login/setup).
- Backend pytest suite: `backend/tests/` — `test_api_auth.py`,
  `test_api_crud.py`, `test_borg_runner.py`, `test_crypto_and_security.py`,
  `test_host_service.py`, `test_repo_service.py` (per the commit message, 32
  tests total covering crypto, auth, command building/parsing, service
  orchestration, API CRUD). **Not re-run during this research pass** — this
  session's Python (3.14) doesn't have `pytest` installed, so test currency
  wasn't verified; CI (`.github/workflows/ci.yml`) runs them on Python 3.10
  and 3.12 via GitHub Actions on push to `master` and on PRs.
- Frontend: builds via Vite; CI runs `npm ci && npm run build`. Per the
  README, it was "visually verified end-to-end (login through creating a
  credential/repo and viewing its detail page)" via a headless-browser smoke
  pass, in an environment with no interactive display.
- Docker Compose deployment (`docker-compose.yml`): `backend` (FastAPI + borg
  + borgmatic + openssh-client baked into the image) and `web` (built SPA
  served by Caddy, which also reverse-proxies `/api/*`).

**What's explicitly NOT verified (the biggest open risk):**
- **`borg_runner.py`'s output parsing has never run against a real Borg
  installation.** It was written against Borg's documented JSON schemas /
  typical text output, but the development sandbox had no network access and
  couldn't build Borg's native extensions, so nothing here has touched a live
  `borg info --json` / `borg list --json` / `borg prune` output. See
  `docs/BORG_COMPATIBILITY.md` for exactly which fields are at risk
  (`parse_info`'s `cache.stats` block, `parse_prune`'s `Would prune:` /
  `Pruning archive` line-counting) and the manual verification commands to
  run once there's a real repo to point it at. Failure mode is graceful
  (fields come back `null`/`0`, raw output always preserved on the run
  record) but the dashboard numbers should not be trusted until this is done.
- Was written with Borg 1.2.x's CLI/output shapes in mind; Borg 2.x changed
  repository format and some command syntax and would need adjustments.
- No production deployment has happened yet as far as this repo shows — no
  evidence of it having been pointed at the owner's actual Proxmox/Nextcloud
  Borg backup host.
- No rate limiting or 2FA on login; SSH host-key verification defaults to
  trust-on-first-use for both repo access and client access (see
  `docs/SECURITY.md` for how to harden both once this goes past a trusted
  network).

## 4. The `_old_agent_deprecated` directory

Contains an **earlier, broken prototype** of a completely different design:
a standalone Python backup *engine* (not a portal) — `backup_engine.py`,
`browser_engine.py`, `restore_engine.py`, `storage_engine.py`,
`crypto_engine.py`, `index_engine.py`, `prune_engine.py`, `health_engine.py`,
`config_manager.py`, `update_engine.py`, `auto_update.py`, `troubleshoot.py`,
plus a `_old_root/` subfolder with an old CLI, installer, run scripts, and
stray test files.

This directory **was never committed to git** (confirmed via `git log --all
-- _old_agent_deprecated`, no history) and is explicitly gitignored
(`.gitignore` has `_old_agent_deprecated/`). It matches the description in
commit `aa92e2d`'s message of "the previous prototype" that "crashed on
startup (RestoreEngine/BrowserEngine constructor mismatches), generated a new
random encryption key every process restart (making backups permanently
undecryptable), had two conflicting UpdateEngine/config implementations, and
had no automation story."

That prototype was superseded by commit `aa92e2d` ("Rebuild Haven Backup:
pluggable local/SFTP backends..."), which itself built a *different* design —
a standalone encrypted/deduplicated backup engine with pluggable
local/SFTP storage backends (this became the root-level `haven_backup/`
package and `tests/`). **That design was then itself superseded** by the
current Borg-control-plane-portal pivot (commit `8803576`), which is what
`backend/`, `frontend/`, and the current `docs/` describe.

**Net effect: `_old_agent_deprecated/` is two generations behind current and
irrelevant to any future work.** It's local-disk clutter only (never in git,
so it doesn't even show up for anyone else who clones the repo). Safe to
delete outright; nothing in it should be referenced or revived. A new session
should treat `backend/`, `frontend/`, and `docs/` as the only current source
of truth.

**Related clutter also found:** the root-level `haven_backup/` and `tests/`
directories (from the *second*-generation SFTP/local-backend design, commit
`aa92e2d`) still exist on disk but now contain **only `__pycache__`
directories** — their actual `.py` source files were deleted in the pivot
commit (`8803576`, confirmed via `git log --stat`: e.g. `haven_backup/backup_engine.py | 142
--`). These two directories are effectively empty (pycache only, gitignored)
and can be deleted along with `_old_agent_deprecated/` — they are not
current either.

## 5. Deployment

`docker-compose.yml` at repo root defines two services:
- `backend` — builds from `./backend` (Dockerfile bakes in `borg`,
  `borgmatic`, `openssh-client`), mounts a `haven_data` named volume at
  `/data`, `HAVEN_DATA_DIR=/data`. Configurable via commented-out env vars in
  the compose file: `HAVEN_NOTIFICATION_WEBHOOK_URL`,
  `HAVEN_STATUS_REFRESH_MINUTES`, `HAVEN_PRUNE_INTERVAL_HOURS`.
- `web` — builds from `./frontend`, exposes `8080:80`, depends on `backend`.
  This is Caddy serving the built SPA and reverse-proxying `/api/*` to
  `backend` internally, so the browser only ever talks to one origin (no
  CORS/cross-origin cookie concerns).

Quick start per README: `git clone ... && cd haven-backup && docker compose
up -d --build`, open `http://<host>:8080`, create the first admin account
(`POST /api/auth/setup`, only available while no users exist), add an SSH
credential, add a repo, click "Refresh now".

Bare-metal/systemd path is documented in `docs/DEPLOYMENT.md` (needs `borg`,
`borgmatic`, `openssh-client` on the portal host itself; a sample systemd
unit is included there).

Put Haven Backup's own `web` container behind the owner's existing reverse
proxy (Caddy per standing project convention) for TLS — it's plain HTTP
inside the Compose network by design.

**Note the GitHub repo description is stale**: `gh repo view` shows
"Encrypted, deduplicated backups for servers and workstations, over local
disk or SFTP" — that's the *old* (generation-2) self-contained-engine
description, predating the Borg-portal pivot. Worth updating on GitHub if/when
convenient; not something in the repo content itself, so it wasn't touched
here.

## 6. Known issues / open work

- **Top priority**: validate `borg_runner.py`'s parsing against a real Borg
  repo/installation (see section 3 and `docs/BORG_COMPATIBILITY.md` for the
  exact commands to run and which functions to fix if shapes don't match:
  `parse_info`, `parse_list`, `parse_prune`).
- No evidence this has been deployed against the owner's actual
  Proxmox/Nextcloud Borg backup host yet — first real deployment + the
  "Refresh now" sanity check from `docs/DEPLOYMENT.md` step 4 is still
  outstanding.
- No TODO/FIXME/XXX comments found anywhere in `backend/app` or
  `frontend/src` (checked via grep) — the "not yet done" list lives entirely
  in the docs' prose (BORG_COMPATIBILITY.md, README's Status section), not in
  code comments.
- Delete `_old_agent_deprecated/`, root `haven_backup/`, and root `tests/`
  (all pycache-only or fully superseded, none tracked in the current design)
  — housekeeping, not urgent, but see section 4.
- `gh issue list --state all` returned no results (command succeeded, empty
  output) — no open or closed GitHub issues currently tracked for this repo.
- Hardening noted as deliberately deferred in `docs/SECURITY.md`: no rate
  limiting/2FA on login, SSH host-key verification is trust-on-first-use by
  default for both repo and client access (instructions included for
  tightening both once this is exposed beyond a trusted network).
- `git status` at time of writing: **clean, nothing uncommitted**, on
  `master`, up to date with `origin/master`.

## 7. Recent history highlights

Full history is only 3 commits, all from 2026-09-09, and each one is a
near-total rewrite of the last:

1. `aa92e2d` — "Rebuild Haven Backup: pluggable local/SFTP backends, working
   CLI, tests, docs." Fixed a broken prior prototype (the one now sitting in
   `_old_agent_deprecated/`, never committed) and built a self-contained
   encrypted/deduplicated backup engine (`haven_backup/` package) with
   `LocalBackend`/`SFTPBackend` storage backends, a non-interactive CLI,
   retention pruning + GC, systemd timer units, and a pytest suite.
2. `ee92598` — "Fix CI trigger branch (master, not main)." One-line CI fix.
3. `8803576` — "Pivot to a Borg control-plane portal (replaces the standalone
   backup agent)." **Current state.** Reasoning per commit message: the owner
   already runs a Borg-based backup server, so a custom storage engine was
   redundant — Borg already does dedup/encryption well. Removed the entire
   `haven_backup/` self-contained engine, its CLI, systemd units, and
   generation-2 docs; replaced with the FastAPI+React portal described
   throughout this file. This is the commit that produced the current
   `backend/`, `frontend/`, `docker-compose.yml`, and `docs/*` content.

No commits since the pivot — the portal design as described in section 2-3
is the entirety of what exists past that point.

## 8. Pointers

- `README.md` — project pitch, stack summary, quick start, file layout map,
  honest "Status" section (matches what's written above)
- `docs/ARCHITECTURE.md` — the two-remote-access-paths design, why retention
  is centralized in the portal, background jobs, Borg version compatibility
  caveat
- `docs/DEPLOYMENT.md` — Docker Compose (primary) and bare-metal/systemd
  paths, full env var reference table, first-run steps
- `docs/BORGMATIC_INTEGRATION.md` — how to configure each client's own
  `borgmatic.yaml` so it doesn't fight the portal's `prune`, what exact
  command "backup now" runs, a borgmatic-version caveat for older clients
- `docs/BORG_COMPATIBILITY.md` — **read before trusting the dashboard** —
  exact verification commands and which parser functions to patch if a Borg
  version's output shape differs
- `docs/SECURITY.md` — encryption-at-rest scope/limits, login model, SSH
  host-key verification defaults and how to harden them, key materialization
  for `borg` subprocess invocations
- `backend/tests/` and CI (`.github/workflows/ci.yml`) — where to look for
  current automated verification; note this session did not confirm the
  suite still passes (no `pytest` available in this environment's Python
  3.14) — a new session with a working `backend/.venv` should run `pytest -q
  tests/` from `backend/` as a first sanity check before further changes

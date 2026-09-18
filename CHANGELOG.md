# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-09-17

### Added
- Interactive setup script (`scripts/setup.sh`) that writes `.env` and brings
  the stack up, alongside the existing manual walkthrough -- see
  `docs/DEPLOYMENT.md`.
- `scripts/update.sh [<tag>]` -- deploys latest, or an exact tagged version
  (code only; refuses to run over uncommitted changes, takes its own
  pre-restart snapshot of the portal's own data regardless of any other
  backup schedule, and polls `/api/health` after restarting before declaring
  success). Rolling back to a tag never implies rolling back the database to
  match -- that stays a separate, manual, deliberate step (see
  `docs/BACKUP.md`). Each shipped version from here on is git-tagged
  (`v0.2.0`, etc.) so there's something for it to target.
- `.env.example` documenting every `HAVEN_*` configuration variable.
- Rate limiting on `/api/auth/login` and `/api/auth/setup` (in-memory, fixed
  window, configurable via `HAVEN_LOGIN_RATE_LIMIT_*`).
- `secure` flag on the session cookie (`HAVEN_COOKIE_SECURE`, default on).
- `/api/health` now actually exercises the database instead of only
  confirming the process is running, and reports the running version.
- `backend/scripts/create_user.py` to add additional admin users (there's no
  signup endpoint beyond the one-time first-run `/api/auth/setup`).
- Structured log format (timestamp/level/logger name) via `logging.basicConfig`.
- App version surfaced in the UI footer and `/api/health`.
- `docs/BACKUP.md` covering how to back up the portal's own database and
  secrets (distinct from the Borg repos it manages).
- Committed Playwright smoke script (`frontend/scripts/smoke.mjs`) for a
  repeatable headless-browser sanity pass instead of an ad hoc, throwaway one.

### Changed
- `docker-compose.yml` now reads configuration from a root `.env` file
  instead of requiring hand-edits to the tracked compose file.

## [0.1.0] - 2026-09-09

### Changed
- **Pivoted the entire project.** Haven Backup is now a web portal
  (FastAPI + React) that configures and monitors existing Borg repositories
  and `borgmatic` clients, rather than a standalone backup engine -- the
  owner already runs a Borg-based backup server, so building/maintaining a
  custom encrypted/deduplicated storage engine was redundant.
- Removed the self-contained local/SFTP backup engine, its CLI, systemd
  units, and generation-2 docs (superseded by the portal).

### Added
- Backend: FastAPI + SQLModel/SQLite, `borg`/`borgmatic` run locally via
  `BORG_RSH` for repo monitoring/retention, `paramiko` SSH for remotely
  triggering a client backup, AES-256-GCM secrets-at-rest, bcrypt + signed
  session cookie auth, APScheduler background jobs (status refresh,
  scheduled pruning, webhook alerts on health transitions).
- Frontend: React + Vite + Tailwind SPA (dashboard, repo detail, client
  hosts, credentials, login/setup).
- Docker Compose deployment (FastAPI backend + Caddy serving the SPA and
  reverse-proxying `/api`).
- Docs: `ARCHITECTURE.md`, `DEPLOYMENT.md`, `BORGMATIC_INTEGRATION.md`,
  `BORG_COMPATIBILITY.md`, `SECURITY.md`.
- 32-test pytest suite; CI on Python 3.10/3.12 plus a frontend build check.

# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-28

First 1.0 release: new machines can now be set up for backup with one command,
and the portal has been run end to end against real Borg repositories.

### Added
- **One-line client enrollment.** **Client Hosts → Enroll a new host** generates a
  one-time install command (`curl … /api/enroll/install.sh | sudo bash -s -- --portal … --token …`)
  for a Debian/Ubuntu/Proxmox machine. The script installs borgbackup + borgmatic,
  creates the client's own key for the backup server, registers the host, repo and a
  dedicated "backup now" credential with the portal, and writes
  `/etc/borgmatic/haven.yaml` in the right format for the installed borgmatic (sectioned
  for < 1.8, flat for 1.8+). It also adds a systemd timer and an `authorized_keys` line
  that forces the portal's key to run only `borgmatic … create --stats`. The one manual
  step, adding the client's key to the backup server, is printed by the script and shown
  in the portal. After that the script creates the repo and starts the first backup. It
  supports `--dry-run`, `--uninstall`, resuming by re-running without a token, and
  refuses a plain-http portal unless given `--allow-http`. Tokens are single-use, stored
  hashed, expire after `HAVEN_ENROLLMENT_TOKEN_TTL_MINUTES` (default 60), and the claim
  endpoint is rate-limited. The client public key is strictly validated, so a claim can't
  smuggle extra keys or options into the line pasted on the backup server. Full guide
  and a manual walkthrough that ends in the same state: `docs/CLIENT_ENROLLMENT.md`.
- **One-line portal installer**, `scripts/install.sh`: checks for git, Docker, the
  Compose plugin and Docker access, clones into `~/haven-backup` (or `--dir`), optionally
  pins a release with `--version`, and runs `setup.sh`. It installs no system packages.
- `docs/WINDOWS_CLIENTS.md`: why Windows clients aren't supported yet and the options
  being considered (WSL2, WSL2 + VSS, a Windows-native tool).
- `.gitattributes` forcing LF on `*.sh`. A CRLF checkout on Windows would otherwise build
  an image that serves a broken client script.

### Fixed
- **"Backup now" failed on any freshly built image.** paramiko 4+ removed `DSSKey`, and
  the key loader referenced it unconditionally. The resulting `AttributeError` also
  escaped `execute_run`, so the run stayed on "running" forever. Both are fixed: DSS is
  only tried where paramiko still has it, and any unexpected error now marks the run
  `failed` with the error in its log.
- **Refresh failed on freshly built images.** Current sqlmodel refuses naive datetimes,
  and `borg list` archive times were stored naive. They're now converted to UTC.
- **Dashboard showed the chunk count as the number of archives.** Borg 1.x `info --json`
  has no `archive_count`, and the parser fell back to `total_chunks`. The count now comes
  from `borg list`. Found by running the portal against real repos for the first time;
  see `docs/BORG_COMPATIBILITY.md`.
- The layout now stacks on narrow screens (nav above the content) instead of squeezing
  the sidebar and page side by side, and wide tables scroll inside their card.
- Full-width fields in the Add host form (`col-span-2` was applied to the `<input>`
  instead of its grid cell, so it never took effect).
- `frontend/package-lock.json`'s version had drifted to 0.5.0.
- The Repositories page help said the portal never creates repos; it now points new
  machines to enrollment, which does.

## [0.5.3] - 2026-09-22

### Added
- Table of contents + a nav row (back to `README.md`, plus links to every
  sibling doc) on every doc in `docs/` -- none of them had one before, and
  most had grown past a single screen. Anchors added via explicit
  `<a id="...">` tags rather than relying purely on GitHub's auto-slugger,
  so existing cross-doc links (`SECURITY.md#ssh-keys-used-for-client-backup-now`,
  etc.) keep working unchanged alongside the new ones.
- Explicit "what success looks like" text after each command/step in the
  procedural docs (`DEPLOYMENT.md`, `BACKUP.md`,
  `RESTRICTED_SSH_ACCOUNTS.md`, `BORG_COMPATIBILITY.md`) -- e.g. what
  `docker compose up -d --build` should print when it worked, what
  `borg info` against a restricted account should return, how to confirm a
  restore actually brought back the version you meant to. Previously most
  steps only showed the command, leaving "did that actually work" to
  inference.

### Fixed
- `README.md`'s "Current version" line had drifted to `0.5.0` across the
  last two patch releases (`0.5.1`, `0.5.2`) -- corrected, and re-verified
  it's part of what gets checked at each release from now on.

## [0.5.2] - 2026-09-18

### Added
- `docs/RESTRICTED_SSH_ACCOUNTS.md`: a "Changing the restricted path later"
  section covering how to actually edit an existing restricted account's
  `authorized_keys` entry -- the original setup command used `>>`, which
  only appends, so re-running it with a different `--restrict-to-path`
  leaves two conflicting `command=` lines instead of replacing the
  restriction. Covers editing in place, a `sed` one-liner for scripting it,
  why no service restart is needed, and that the repo's `ssh://` URL in the
  portal has to be updated to match. Linked from the SSH Credentials page's
  contextual help.

## [0.5.1] - 2026-09-18

### Added
- `docs/RESTRICTED_SSH_ACCOUNTS.md` -- how to set Haven Backup up against a
  backup host that already locks other apps down to their own restricted
  SSH account (`command="borg serve --restrict-to-path ..."` in
  `authorized_keys`, no shell) instead of a shared full-access login,
  including the append-only-vs-retention tradeoff (an append-only account
  can't be pruned by design, which shows up as a permission error, not a
  bug, if you set a retention policy against one). Cross-linked from
  `SECURITY.md`, `DEPLOYMENT.md`, `README.md`, and the SSH Credentials and
  Repositories pages' contextual help in the UI. Requested directly rather
  than inferred -- some of the backup server's existing accounts are
  already locked down this way for other apps.

## [0.5.0] - 2026-09-18

### Added
- Contextual, per-page help: a collapsible "Show help"/"Hide help" box on
  Dashboard, SSH Credentials, Client Hosts, Repositories, and a repo's
  detail page, each with a real walkthrough for what that specific page
  does -- generating and installing an SSH key, initializing a repo with
  `borg init` before adding it here (this portal never creates repos, only
  monitors existing ones), what "backup now" actually runs, how retention
  and restoring work. Collapse state is remembered per browser
  (localStorage), defaulting open. The central `/help` page is trimmed to
  just what isn't specific to one page (updating, password reset,
  security, doc links) instead of duplicating the above.
- `GET /api/runs/checks` (list) and a "Recent checks" card on a repo's
  detail page. Previously an integrity check's result only existed in the
  popup shown right when you started it -- closing that popup or navigating
  away lost track of it entirely, with no way to see whether it had passed
  or failed afterward. Found this gap while writing the help text for that
  button and realizing it described something not actually true yet.

### Tests
- `backend/tests/test_api_runs.py` -- no endpoint under `/api/runs` had any
  test coverage before this (list/get for backups, prunes, and the new
  checks list; auth requirement).

## [0.4.0] - 2026-09-18

### Added
- `backend/scripts/reset_password.py` -- resets an existing user's password
  (interactively, or `--generate` for a one-time random password printed to
  the terminal). There was previously no supported way to do this short of
  hand-writing a DB update; this replaces that with a proper, tested script,
  documented alongside `create_user.py`.
- In-app **Help** page (`/help`, linked from the sidebar): getting started,
  retention/pruning, restoring, updating, the password-reset commands above,
  a security summary, and links out to the full docs on GitHub. Previously
  this was deliberately skipped as a personal single-operator tool with no
  other users -- added on request.

### Known issue
- The app's overall layout (sidebar + content) doesn't stack on narrow
  viewports -- checked the new Help page on a 390px-wide mobile viewport and
  found the whole app (not just this page) squeezes sidebar and content
  side by side instead of stacking, making everything cramped. Pre-existing,
  not introduced by this release; not fixed here since it wasn't in scope of
  what was asked, but worth fixing.

## [0.3.0] - 2026-09-18

### Added
- The running app version is now stamped into the database itself on every
  startup (`AppMeta` table, `backend/app/version_stamp.py`), so a backup
  snapshot is self-identifying instead of relying on file-modified-time
  guessing. `scripts/update.sh` and the manual commands in `docs/BACKUP.md`
  now label pre-update/backup snapshots by that stamped version (queried
  from the still-running container before it's rebuilt), not the git tree.
- `GET /api/version` and a UI hint (sidebar footer badge) showing whether a
  newer tagged release exists, via GitHub's public tags API -- visibility
  only, not a trigger. Opt-out via `HAVEN_UPDATE_CHECK_ENABLED=false` for
  fully offline operation; cached for an hour to avoid hammering the API.
  Deliberately does not attempt to trigger the actual update from the UI --
  the container has no git checkout or Docker socket access to rebuild
  itself, and adding a `docker.sock` passthrough just for this wasn't judged
  worth the added attack surface on a tool that already holds SSH keys and
  Borg passphrases (see `docs/SECURITY.md`).
- `backend/scripts/db_version.py`, used by the above.

### Fixed
- `backend/Dockerfile` never copied `scripts/` into the image, so
  `backend/scripts/create_user.py` -- already documented as the way to add
  a second admin user -- would have failed with "file not found" the first
  time anyone actually tried it in the real container. Caught while wiring
  up `db_version.py`, which needed the same fix.
- `frontend/scripts/smoke.mjs` flagged the expected pre-login `/api/auth/me`
  401 as a failure; narrowed to actual unexpected HTTP errors.
- The update-check cache's "never checked" sentinel (`checked_at = 0.0`,
  compared against `time.monotonic()`) could read as "checked recently" on
  a freshly started process, since that clock's reference point is
  undefined and can be small right after boot -- silently reporting
  `latest: null` for up to an hour after every container restart. Caught by
  CI failing deterministically (young runner, small clock) while passing
  locally every time (long-uptime dev machine); fixed by using `-inf` as
  the sentinel instead of `0.0`.
- `test_tampered_session_token_rejected` was genuinely flaky (~1-in-10):
  tampering with the *last* character of a base64-encoded signature can
  decode to identical bytes when that segment's bit-length isn't a
  multiple of 6, since the low bits are unused padding -- some replacement
  characters left the signature still valid. Fixed by tampering with the
  signature's first character instead, which is always fully significant.

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

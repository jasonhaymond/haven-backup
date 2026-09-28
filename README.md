# Haven Backup

**Current version: 1.0.0** -- see [CHANGELOG.md](CHANGELOG.md) for release history.

A web portal to configure and monitor **Borg** backups across your servers --
Proxmox, Nextcloud, whatever else you run -- from one place. It doesn't do
the backing up itself (Borg already does that well); it sits in front of your
existing Borg repos and borgmatic clients to give you:

- **A dashboard** of every repo: last archive time, size, dedup stats, and a
  health/staleness badge, so a silently-broken backup job doesn't stay silent.
- **Centralized retention** -- set a `keep_daily`/`weekly`/`monthly`/`yearly`
  policy per repo in the portal, and it runs `borg prune` on a schedule (or on
  demand, dry-run first) directly against the repo -- no need for every
  client's own borgmatic config to agree on the rules.
- **Remote "backup now"** -- SSH into a client host and trigger a real
  `borgmatic create` run, from the UI.
- **One-line client enrollment** -- generate a command in the portal, run it
  on a new Debian/Ubuntu/Proxmox machine, paste one line on the backup
  server, and it's backing up on a schedule and showing on the dashboard
  (borgmatic config, systemd timer, repo, and a locked-down "backup now"
  key, all set up for you) -- see [docs/CLIENT_ENROLLMENT.md](docs/CLIENT_ENROLLMENT.md).
- **Integrity checks** (`borg check`) and full run history/logs for every
  backup, prune, and check, all from the browser.
- **Update-available visibility** in the UI (not a trigger) -- see
  [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#updating-and-rolling-back).
- **Contextual help on every page** -- a collapsible walkthrough for what
  that specific page does (generating an SSH key, initializing a repo,
  what "backup now" runs), plus a central `/help` page in the UI for
  cross-cutting topics (updating, password reset, security, full docs).

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit
together, and why monitoring/retention and "backup now" reach your
infrastructure in two different ways.

## Stack

- **Backend**: FastAPI + SQLModel (SQLite), running `borg`/`borgmatic` as
  local subprocesses and SSHing into client hosts via `paramiko`.
- **Frontend**: React + Vite + Tailwind, talking to the backend's JSON API.
- Login is built in (bcrypt + signed session cookies) -- see
  [docs/SECURITY.md](docs/SECURITY.md).

## Quick start

On a host with Docker and git already installed:

```bash
curl -fsSL https://raw.githubusercontent.com/jasonhaymond/haven-backup/master/scripts/install.sh | bash
```

That clones the repo and runs the interactive setup. The same thing by hand:

```bash
git clone https://github.com/jasonhaymond/haven-backup.git
cd haven-backup
./scripts/setup.sh
```

(Or skip the script and run `docker compose up -d --build` directly after
copying `.env.example` to `.env` -- see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
for the full manual walkthrough, which ends in the same place.)

Open `http://<host>:8080`, create the first admin account, then:
1. Add an **SSH credential** for your Borg backup host.
2. Add a **repository** (its `ssh://` URL + that credential + its passphrase
   + a retention policy) and click **Refresh now**.
3. Add machines to back up: **Client Hosts → Enroll a new host** gives you a
   one-line install command for a new Debian/Ubuntu/Proxmox machine
   ([docs/CLIENT_ENROLLMENT.md](docs/CLIENT_ENROLLMENT.md)). Or, for a machine
   where borgmatic is already set up by hand, add a **client host** (with its own
   SSH credential and borgmatic config path) to enable "backup now" -- read
   [docs/BORGMATIC_INTEGRATION.md](docs/BORGMATIC_INTEGRATION.md) first so
   retention ownership between the portal and each client's own borgmatic
   config doesn't conflict.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the bare-metal/systemd path,
configuration via environment variables, and reverse-proxy notes.

## Full documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) -- how monitoring, retention, and remote triggering actually reach your infrastructure
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) -- one-line install, Docker Compose and bare-metal setup, environment variables
- [docs/CLIENT_ENROLLMENT.md](docs/CLIENT_ENROLLMENT.md) -- adding a machine to back up with one command (plus the full manual equivalent)
- [docs/WINDOWS_CLIENTS.md](docs/WINDOWS_CLIENTS.md) -- why Windows clients aren't supported yet, and the options being considered
- [docs/BORGMATIC_INTEGRATION.md](docs/BORGMATIC_INTEGRATION.md) -- how this coexists with your existing borgmatic clients, and why the portal should own `prune`
- [docs/RESTRICTED_SSH_ACCOUNTS.md](docs/RESTRICTED_SSH_ACCOUNTS.md) -- setting Haven Backup up against a locked-down/restricted account on the backup server, if your backup host already does per-app accounts (and the append-only/retention tradeoff that comes with it)
- [docs/BORG_COMPATIBILITY.md](docs/BORG_COMPATIBILITY.md) -- **verify this against your Borg version before trusting the dashboard numbers**
- [docs/SECURITY.md](docs/SECURITY.md) -- what's encrypted at rest, SSH host key verification, session/login model, rate limiting
- [docs/BACKUP.md](docs/BACKUP.md) -- backing up (and restoring -- tested) the portal's own database and secrets
- [CHANGELOG.md](CHANGELOG.md) -- release history

## How it's laid out

```
backend/app/
  main.py            FastAPI app, CORS, lifespan (DB init + scheduler)
  models.py          SQLModel tables: users, credentials, hosts, repos, run history
  borg_runner.py     builds/runs borg commands locally (BORG_RSH over ssh://), parses output
  ssh_exec.py        paramiko: SSH into a client host to trigger borgmatic
  repo_service.py    Repo <-> borg_runner glue: refresh status, prune, check
  host_service.py    ClientHost <-> ssh_exec glue: trigger a backup run
  enrollment.py      one-line client enrollment: tokens, keys, rendering the client's config/units
  static/client-install.sh  the client install script served at /api/enroll/install.sh
  scheduler.py       periodic status refresh + scheduled pruning + staleness alerts
  crypto.py          encrypts SSH keys/passphrases at rest
  security.py        password hashing, signed session cookies
  rate_limit.py       in-memory rate limiting for login/setup
  version_stamp.py    stamps the running version into the DB on every startup
  routers/           the JSON API (auth, credentials, hosts, repos, runs, dashboard, version, enrollments)
backend/scripts/
  create_user.py     add an admin user after initial setup
  reset_password.py  reset an existing user's password (no self-service "forgot password" in the UI)
  db_version.py      print the version stamped in the database (used by the update/backup scripts)
frontend/src/
  pages/             Dashboard, Repositories, Repo detail, Client Hosts, Credentials, Login/Setup, Help
  components/        HelpBox.jsx (per-page contextual help, collapsible), RunStatusModal, ui.jsx
  context/           auth state
  lib/                fetch client, formatting, run-status polling, docs links
frontend/scripts/
  smoke.mjs          headless-browser sanity pass (login -> create credential/repo -> view detail)
scripts/
  install.sh         one-line installer: clones the repo, then runs setup.sh
  setup.sh           interactive Docker Compose setup (writes .env, brings up the stack)
  update.sh          deploy latest or roll back to a tagged version (code only -- see docs/BACKUP.md)
```

## Status

This is a personal-infrastructure tool, not a widely-audited product. As of
1.0.0 the whole path has been run end to end against real Borg: a Debian 12
and an Ubuntu 24.04 client enrolled with the one-line installer (systemd
timer, first backup, "backup now", forced-command key restrictions), and the
portal's `info`/`list`/`prune`/`check` parsing checked against those repos
(borg 1.4.0 in the portal, 1.2.x on clients and the backup server -- see
[docs/BORG_COMPATIBILITY.md](docs/BORG_COMPATIBILITY.md) for other versions).
Also exercised directly, not just assumed: the backend's pytest suite (82 tests: crypto, auth, rate limiting,
command building/output parsing, service orchestration, API CRUD, run
history endpoints, version stamping/update-check, password reset/creation
scripts, client enrollment incl. rejecting smuggled SSH keys); the full Docker Compose build and a real
destroy-and-restore cycle of the portal's own data volume
([docs/BACKUP.md](docs/BACKUP.md)); and the frontend, end-to-end in a real
headless browser (login through creating a credential/repo and viewing its
detail page -- `frontend/scripts/smoke.mjs`), which is also how a real
session cookie bug (`Secure` over plain HTTP silently breaking login) and a
missing `COPY scripts` in the Dockerfile both got caught before shipping.

Known, stated gaps rather than oversights: no database migration tool yet
(schema changes need manual handling -- see [docs/BACKUP.md](docs/BACKUP.md));
update-available is visible in the UI, but triggering the actual update from
there isn't built -- `scripts/update.sh` on the host is the documented path
(see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/SECURITY.md](docs/SECURITY.md)
for why); no frontend unit-test suite (the Playwright smoke script covers
the main paths, not every edge case); client enrollment supports apt-based
Linux only (Windows: [docs/WINDOWS_CLIENTS.md](docs/WINDOWS_CLIENTS.md)).

## License

MIT -- see [LICENSE](LICENSE).

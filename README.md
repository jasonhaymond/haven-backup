# Haven Backup

**Current version: 0.3.0** -- see [CHANGELOG.md](CHANGELOG.md) for release history.

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
- **Integrity checks** (`borg check`) and full run history/logs for every
  backup, prune, and check, all from the browser.
- **Update-available visibility** in the UI (not a trigger) -- see
  [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#updating-and-rolling-back).

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
3. Optionally add a **client host** (with its own SSH credential and
   borgmatic config path) to enable "backup now" -- read
   [docs/BORGMATIC_INTEGRATION.md](docs/BORGMATIC_INTEGRATION.md) first so
   retention ownership between the portal and each client's own borgmatic
   config doesn't conflict.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the bare-metal/systemd path,
configuration via environment variables, and reverse-proxy notes.

## Full documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) -- how monitoring, retention, and remote triggering actually reach your infrastructure
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) -- Docker Compose and bare-metal setup, environment variables
- [docs/BORGMATIC_INTEGRATION.md](docs/BORGMATIC_INTEGRATION.md) -- how this coexists with your existing borgmatic clients, and why the portal should own `prune`
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
  scheduler.py       periodic status refresh + scheduled pruning + staleness alerts
  crypto.py          encrypts SSH keys/passphrases at rest
  security.py        password hashing, signed session cookies
  rate_limit.py       in-memory rate limiting for login/setup
  version_stamp.py    stamps the running version into the DB on every startup
  routers/           the JSON API (auth, credentials, hosts, repos, runs, dashboard, version)
backend/scripts/
  create_user.py     add an admin user after initial setup
  db_version.py      print the version stamped in the database (used by the update/backup scripts)
frontend/src/
  pages/             Dashboard, Repositories, Repo detail, Client Hosts, Credentials, Login/Setup
  context/           auth state
  lib/                fetch client, formatting, run-status polling
frontend/scripts/
  smoke.mjs          headless-browser sanity pass (login -> create credential/repo -> view detail)
scripts/
  setup.sh           interactive Docker Compose setup (writes .env, brings up the stack)
  update.sh          deploy latest or roll back to a tagged version (code only -- see docs/BACKUP.md)
```

## Status

This is a personal-infrastructure tool, not a widely-audited product, and its
Borg output parsing hasn't been validated against a live Borg installation
(see [docs/BORG_COMPATIBILITY.md](docs/BORG_COMPATIBILITY.md) -- please check
this against your setup). What *has* been exercised directly, not just
assumed: the backend's pytest suite (45 tests: crypto, auth, rate limiting,
command building/output parsing, service orchestration, API CRUD, version
stamping/update-check); the full Docker Compose build and a real
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
the main paths, not every edge case).

## License

MIT -- see [LICENSE](LICENSE).

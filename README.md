# Haven Backup

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
docker compose up -d --build
```

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
- [docs/SECURITY.md](docs/SECURITY.md) -- what's encrypted at rest, SSH host key verification, session/login model

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
  routers/           the JSON API (auth, credentials, hosts, repos, runs, dashboard)
frontend/src/
  pages/             Dashboard, Repositories, Repo detail, Client Hosts, Credentials, Login/Setup
  context/           auth state
  lib/                fetch client, formatting, run-status polling
```

## Status

This is a personal-infrastructure tool, not a widely-audited product, and its
Borg output parsing hasn't been validated against a live Borg installation
(see [docs/BORG_COMPATIBILITY.md](docs/BORG_COMPATIBILITY.md) -- please check
this against your setup). Backend logic (crypto, auth, command building,
output parsing, service orchestration) has a pytest suite; the frontend has
been visually verified end-to-end (login through creating a credential/repo
and viewing its detail page) but hasn't seen a real Borg repo yet either.

## License

MIT -- see [LICENSE](LICENSE).

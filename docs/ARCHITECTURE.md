# Architecture

Haven Backup is a **control-plane portal in front of Borg** -- it does not
itself store or encrypt backup data (Borg already does that). It exists to
give you one place to see whether every repo is healthy, apply retention
consistently, and (optionally) kick off a backup on demand.

```
┌─────────────┐        ssh://user@backup-host/repo         ┌──────────────┐
│   Portal    │ ───────────────────────────────────────────▶│ Backup host  │
│  (backend)  │   `borg info/list/prune/check` run locally  │ (borg serve, │
│             │   by the portal itself, over borg's own     │  Borg repos) │
│             │   SSH transport (BORG_RSH) -- no agent on    └──────────────┘
│             │   the backup host needed for this.
│             │
│             │        SSH exec (paramiko)
│             │ ───────────────────────────────────────────▶┌──────────────┐
└─────────────┘   `borgmatic --config ... create`           │ Client host  │
                   only when you click "backup now"          │ (Proxmox,    │
                                                               │  Nextcloud)  │
                                                               │ own cron/    │
                                                               │ systemd runs │
                                                               │ borgmatic    │
                                                               │ create too   │
                                                               └──────────────┘
```

## Two different remote-access paths, on purpose

- **Repo monitoring and retention** (`borg info`, `borg list`, `borg prune`,
  `borg check`) run as **local subprocesses inside the portal's own
  container/host**, pointed at a repo's `ssh://` URL. `borg` opens its own SSH
  connection for this (the same way `git` does for a `git+ssh` remote) via the
  `BORG_RSH` environment variable -- the portal never needs SSH access to a
  *client* machine to do this, only to the backup host holding the repo.
- **Triggering a backup on a client** (`backup now`) is the one place the
  portal reaches into a *client* machine, over SSH via `paramiko`, to run
  `borgmatic ... create` there (it has to run locally on the client to read
  the client's own filesystem).

## Why retention is centralized here, not in each client's borgmatic config

If each client's own `borgmatic` config also ran `prune` on its own schedule
with its own keep-rules, it would periodically fight the portal over what
gets kept. So: client-side borgmatic should be configured for `create` (and
optionally `check`) only, and the portal is the single owner of `prune` for
every repo it manages -- see [BORGMATIC_INTEGRATION.md](BORGMATIC_INTEGRATION.md).

## Data the portal stores itself

A small SQLite database (`backend/app/models.py`): SSH credentials (private
keys encrypted at rest), client hosts, repos (Borg passphrases encrypted at
rest), and run history for backups/prunes/checks. See
[SECURITY.md](SECURITY.md) for what "encrypted at rest" does and doesn't protect
against.

## Background jobs

An in-process APScheduler (`backend/app/scheduler.py`) periodically:
1. refreshes every repo's status (`borg info` + `borg list`), recording a
   `RepoStatusSnapshot` and firing a webhook notification on a health
   transition (was OK, now failing);
2. runs `prune` for every repo on a fixed interval (default daily).

## Borg version compatibility

`borg info --json` / `borg list --json` parsing, and `borg prune` text-output
parsing, are implemented against Borg's documented/typical output shapes but
have **not been validated against a live Borg installation** in this
project's development environment (no network access to build Borg's native
extensions there). See [BORG_COMPATIBILITY.md](BORG_COMPATIBILITY.md) before
relying on the parsed fields -- the raw command output is always stored
alongside the parsed fields on every run record, specifically so nothing is
lost if a field needs remapping for your Borg version.

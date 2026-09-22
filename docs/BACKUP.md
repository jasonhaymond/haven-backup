# Backing up the portal itself

[← Back to README](../README.md) · [Architecture](ARCHITECTURE.md) ·
[Deployment](DEPLOYMENT.md) · [Borgmatic integration](BORGMATIC_INTEGRATION.md) ·
[Restricted SSH accounts](RESTRICTED_SSH_ACCOUNTS.md) ·
[Borg compatibility](BORG_COMPATIBILITY.md) · [Security](SECURITY.md)

## Contents
- [What actually matters](#what-actually-matters)
- [Version-labeled snapshots](#version-labeled-snapshots)
- [Docker Compose](#docker-compose)
  - [Restoring](#restoring)
- [Bare-metal](#bare-metal)
- [Automating this](#automating-this)
- [No schema migrations yet](#no-schema-migrations-yet)

Haven Backup monitors and prunes *other* things' backups (Borg repos) --
but the portal has its own state too, and it's small enough that there's no
excuse not to back it up: the SQLite database, and the two key files that
protect everything in it.

<a id="what-actually-matters"></a>
## What actually matters

Everything lives under `backend/data/` (bare-metal) or the `haven_data`
Docker named volume (Compose):

| File | What it is |
|---|---|
| `haven.db` | Users, SSH credentials, repos, and run history (SQLite) |
| `secret.key` | Encrypts SSH private keys/Borg passphrases stored in `haven.db` |
| `session.key` | Signs login session cookies |
| `ssh_keys/` | Transient -- a decrypted key is written here immediately before a `borg` call and deleted right after. Normally empty; harmless if a stray file is ever included in a backup. |

**Back up `secret.key` together with `haven.db`, not separately and not on a
different schedule.** Per this project's own [SECURITY.md](SECURITY.md), the
key is what makes every stored SSH key/passphrase in the database readable
at all -- a database backup without the matching key file is not a usable
backup, the same way a database backup without its app's `.env` secrets
isn't either.

<a id="version-labeled-snapshots"></a>
## Version-labeled snapshots

Every time the app starts, it stamps its own version into the database
itself (a single-row `AppMeta` table -- `backend/app/version_stamp.py`).
That's what lets a snapshot be labeled by the version that was actually
*running against that data* at backup time, rather than guessing from a
file's modified-time or from whatever the git tree happens to say (which can
be ahead of what a not-yet-rebuilt container is running). `scripts/update.sh`
already does this automatically for its pre-update snapshot; the manual
commands below show the same technique.

<a id="docker-compose"></a>
## Docker Compose

Take a consistent snapshot by briefly stopping the backend (SQLite doesn't
like being tarred mid-write), then tar the volume. Query the running
container for its stamped version first, while it's still up:

```bash
VERSION=$(docker compose exec -T backend python scripts/db_version.py)
docker compose stop backend
docker run --rm \
  -v haven-backup_haven_data:/data \
  -v "$(pwd)/backups:/backup" \
  alpine tar czf "/backup/haven-data-v${VERSION}-$(date +%Y%m%d-%H%M).tar.gz" -C /data .
docker compose start backend
```

**What success looks like:** `ls -lh backups/` shows a new
`haven-data-v<version>-<timestamp>.tar.gz` file with a non-zero size (a
handful of KB is normal for a small SQLite DB), and
`curl http://localhost:8080/api/health` returns `{"status":"ok",...}` again
once `docker compose start backend` finishes -- confirming the portal came
back up cleanly after the stop.

(Replace `haven-backup_haven_data` with your actual volume name if you
renamed the project directory -- check with `docker volume ls`. On Windows
with Git Bash, put the backup destination inside your project directory
rather than `/tmp`, which isn't reliably shared into Docker Desktop's VM.)

`ls backups/` then doubles as your version-labeled restore list --
`haven-data-v0.2.0-20260917-2300.tar.gz` tells you both what it is and what
was running when it was taken, no separate index needed for a handful of
files. There's no admin-UI backup list for this (see "Automating this"
below for why) -- the directory listing is the list.

Ship that `.tar.gz` off this host -- object storage, another server over
`scp`/`rsync`, whatever you already use elsewhere. A copy sitting next to the
volume it backs up doesn't protect against this host failing.

<a id="restoring"></a>
### Restoring

Verified against this exact procedure (see the note on this project's own
Status/README for the destroy-and-restore test this was checked against):

```bash
docker compose stop backend
docker run --rm \
  -v haven-backup_haven_data:/data \
  -v "$(pwd)/backups:/backup" \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/haven-data-v<version>-<timestamp>.tar.gz -C /data"
docker compose start backend
```

**What success looks like:** `curl http://localhost:8080/api/health` returns
`{"status":"ok","database":true,...}` once the backend restarts, and logging
into the UI shows the credentials/repos/retention policies that existed at
backup time. To confirm you restored the data you meant to -- not a stale or
wrong snapshot -- check the stamped version against the one in the filename
you restored:

```bash
docker compose exec -T backend python scripts/db_version.py
# should print the same version that was in the filename you extracted
```

What this recovers: every configured SSH credential, repo, and its retention
policy, plus full run history -- exactly as of the backup's timestamp. What
it does **not** recover: anything that happened between the backup and
whatever caused you to need it (RPO = your backup interval; there's no
continuous replication here). Recovery time is however long `docker compose
up -d` takes to rebuild + start, typically under a minute.

<a id="bare-metal"></a>
## Bare-metal

Same idea, no Docker layer in the way:

```bash
cd /opt/haven-backup/backend   # wherever the app's WorkingDirectory is
VERSION=$(.venv/bin/python scripts/db_version.py)
systemctl stop haven-backup-portal
tar czf "haven-data-v${VERSION}-$(date +%Y%m%d-%H%M).tar.gz" -C /var/lib/haven-backup .
systemctl start haven-backup-portal
```

**What success looks like:** `ls -lh haven-data-v*.tar.gz` shows the new
archive, and `systemctl status haven-backup-portal` reports `active
(running)` again after the restart.

Restore by stopping the service, extracting the tarball back over
`/var/lib/haven-backup` (or wherever `HAVEN_DATA_DIR` points), and starting
it again -- same "what success looks like" check as the Docker Compose
[Restoring](#restoring) section above: the service comes back `active
(running)`, and `.venv/bin/python scripts/db_version.py` prints the version
from the filename you restored.

<a id="automating-this"></a>
## Automating this

`scripts/update.sh` already takes a version-labeled snapshot automatically
before every deploy/rollback (see [DEPLOYMENT.md](DEPLOYMENT.md)) -- that
covers "before something risky happens." There's no separate
scheduled/one-click backup for routine, nothing-changed days yet (unlike the
Borg repos this portal manages, which it prunes on its own schedule): run
the manual commands above by hand, or put them in your own cron job /
systemd timer pointed at wherever you ship backups to. This is a deliberate,
stated gap, not an oversight -- the portal's own database is small and
low-churn (it only changes when you edit config or a scheduled job records a
run), so a periodic cron entry is proportionate for now rather than building
a dedicated feature for it.

<a id="no-schema-migrations-yet"></a>
## No schema migrations yet

Changing `backend/app/models.py` and restarting currently just adds any
missing tables (`SQLModel.metadata.create_all`) -- it does not alter
existing tables. If a future change needs an actual column change on an
existing table, that's not handled automatically yet; take a backup first
(per this doc) and expect to migrate the data by hand (or drop and let it
recreate, losing existing rows) until this project adopts a real migration
tool (e.g. Alembic). Worth knowing before you accumulate a lot of
irreplaceable SSH credentials/repo config you'd hate to lose to that gap.

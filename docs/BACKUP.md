# Backing up the portal itself

Haven Backup monitors and prunes *other* things' backups (Borg repos) --
but the portal has its own state too, and it's small enough that there's no
excuse not to back it up: the SQLite database, and the two key files that
protect everything in it.

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

## Docker Compose

Take a consistent snapshot by briefly stopping the backend (SQLite doesn't
like being tarred mid-write), then tar the volume:

```bash
docker compose stop backend
docker run --rm \
  -v haven-backup_haven_data:/data \
  -v "$(pwd)/backups:/backup" \
  alpine tar czf /backup/haven-data-$(date +%Y%m%d-%H%M).tar.gz -C /data .
docker compose start backend
```

(Replace `haven-backup_haven_data` with your actual volume name if you
renamed the project directory -- check with `docker volume ls`. On Windows
with Git Bash, put the backup destination inside your project directory
rather than `/tmp`, which isn't reliably shared into Docker Desktop's VM.)

Ship that `.tar.gz` off this host -- object storage, another server over
`scp`/`rsync`, whatever you already use elsewhere. A copy sitting next to the
volume it backs up doesn't protect against this host failing.

### Restoring

Verified against this exact procedure (see the note on this project's own
Status/README for the destroy-and-restore test this was checked against):

```bash
docker compose stop backend
docker run --rm \
  -v haven-backup_haven_data:/data \
  -v "$(pwd)/backups:/backup" \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/haven-data-<timestamp>.tar.gz -C /data"
docker compose start backend
```

What this recovers: every configured SSH credential, repo, and its retention
policy, plus full run history -- exactly as of the backup's timestamp. What
it does **not** recover: anything that happened between the backup and
whatever caused you to need it (RPO = your backup interval; there's no
continuous replication here). Recovery time is however long `docker compose
up -d` takes to rebuild + start, typically under a minute.

## Bare-metal

Same idea, no Docker layer in the way:

```bash
systemctl stop haven-backup-portal
tar czf haven-data-$(date +%Y%m%d-%H%M).tar.gz -C /var/lib/haven-backup .
systemctl start haven-backup-portal
```

Restore by stopping the service, extracting the tarball back over
`/var/lib/haven-backup` (or wherever `HAVEN_DATA_DIR` points), and starting
it again.

## Automating this

There's no scheduled/one-click backup for the portal's own data yet (unlike
the Borg repos it manages, which it prunes on its own schedule) -- run the
commands above by hand, or put them in your own cron job / systemd timer
pointed at wherever you ship backups to. This is a deliberate, stated gap:
the portal's own database is small and low-churn (it only changes when you
edit config or a scheduled job records a run), so a periodic cron entry is
proportionate for now rather than building a dedicated feature for it.

## No schema migrations yet

Changing `backend/app/models.py` and restarting currently just adds any
missing tables (`SQLModel.metadata.create_all`) -- it does not alter
existing tables. If a future change needs an actual column change on an
existing table, that's not handled automatically yet; take a backup first
(per this doc) and expect to migrate the data by hand (or drop and let it
recreate, losing existing rows) until this project adopts a real migration
tool (e.g. Alembic). Worth knowing before you accumulate a lot of
irreplaceable SSH credentials/repo config you'd hate to lose to that gap.

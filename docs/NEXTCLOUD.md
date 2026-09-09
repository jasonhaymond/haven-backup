# Backing up Nextcloud

Nextcloud has three things worth backing up separately, and they need to be
**consistent with each other** -- restoring `config.php` from Tuesday against
a database dump from Thursday will corrupt user data. Take the DB dump
immediately before (or during) the same Haven Backup run.

## 1. Config

```bash
haven-backup config set-backup-paths \
  /var/www/nextcloud/config \
  /etc/apache2/sites-available \
  /etc/nginx/sites-available \
  /etc/php/*/fpm/pool.d
```

`config/config.php` contains your instance secrets (`passwordsalt`,
`secret`, DB credentials) -- this is exactly the kind of thing Haven Backup's
client-side encryption is for.

## 2. Database dump

Add a pre-backup hook that dumps the DB to a path Haven Backup then picks up.
A small wrapper script works well:

```bash
#!/bin/bash
# /usr/local/bin/haven-backup-nextcloud.sh
set -euo pipefail
sudo -u www-data php /var/www/nextcloud/occ maintenance:mode --on
mysqldump --single-transaction -u nextcloud -p"$NEXTCLOUD_DB_PASSWORD" nextcloud \
  > /var/backups/nextcloud/nextcloud-db.sql
sudo -u www-data php /var/www/nextcloud/occ maintenance:mode --off
/opt/haven-backup/.venv/bin/haven-backup backup --type full
```

(For PostgreSQL: `pg_dump nextcloud > /var/backups/nextcloud/nextcloud-db.sql`.)

```bash
haven-backup config set-backup-paths \
  /var/www/nextcloud/config \
  /var/backups/nextcloud
```

Point cron/systemd at this wrapper script instead of `haven-backup backup`
directly, so the DB dump always happens right before the backup that includes it.

## 3. Data directory -- usually *not* through Haven Backup

Nextcloud's `data/` directory (user files) is typically far larger than
config/DB, and is exactly the kind of thing already covered by whatever
you're backing up your storage/disks with (e.g. ZFS snapshots, Proxmox
Backup Server if `data/` lives on a VM disk, or your existing NAS backup).
Running Haven Backup over a large, frequently-changing data directory works,
but chunk-level dedup doesn't help much on already-compressed user files
(photos, videos), and every backup run will be dominated by scanning it.

If you do want it included, exclude Nextcloud's own cache/thumbnail churn:

```bash
haven-backup config set-exclude \
  "*/data/*/cache/*" \
  "*/data/*/thumbnails/*" \
  "*/data/appdata_*/preview/*"
```

## Restoring

1. Restore `config/config.php` and the DB dump from the same snapshot.
2. Import the DB dump.
3. Put `config.php` back in place, run `occ maintenance:mode --off` and
   `occ files:scan --all` if the data directory was restored separately from
   a different backup system.

See [RESTORE.md](RESTORE.md) for the general `haven-backup restore` workflow.

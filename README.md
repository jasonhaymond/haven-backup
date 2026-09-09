# Haven Backup

Encrypted, deduplicated, content-addressable backups for servers and workstations.
Point it at your `/etc`, your Proxmox cluster config, your Nextcloud config and
database dumps -- whatever you don't want to lose -- and it chunks, dedupes,
and encrypts everything client-side before it ever leaves the machine.

## Features

- **Client-side AES-256-GCM encryption** -- the destination (including a remote
  SFTP host) only ever sees encrypted chunks. The key never leaves the source machine.
- **Content-addressable dedup** -- identical chunks across files and across
  snapshots are stored once.
- **Two destinations, same engine** -- write to a local path (which can be an
  NFS/SMB/sshfs mount) or push directly over **SFTP** to a remote backup host,
  with no mount required.
- **Resumable backups** -- a killed/interrupted run picks back up where it left
  off on the next `backup` invocation instead of starting over.
- **Retention + pruning** -- keep N full and M incremental snapshots; `prune`
  deletes the rest and garbage-collects any chunk nothing references anymore.
- **Cron/systemd-friendly CLI** -- every command needed for unattended backups
  (`backup`, `healthcheck`, `prune`) is non-interactive with meaningful exit codes.
- **Exclude patterns** -- skip logs, caches, VM disk images, whatever you don't
  want in scope.

## Quick start

```bash
git clone https://github.com/jasonhaymond/haven-backup.git
cd haven-backup
pip install -e .
haven-backup init
haven-backup config set-backup-paths /etc /etc/pve
haven-backup config set-exclude "*.log" "*/cache/*"
haven-backup backup --type full
haven-backup snapshots
haven-backup restore <snapshot_id> full --to /tmp/restore-test
```

By default, backups go to a local repo at `~/.haven_backup/haven_backup_repo`
(point that path at a mount if you want a network destination). To push to a
remote host over SFTP instead:

```bash
haven-backup config set-destination sftp \
  --host backup.example.com --username haven \
  --remote-path /mnt/backups/$(hostname) \
  --key-path ~/.ssh/id_ed25519
```

See [docs/SFTP_SETUP.md](docs/SFTP_SETUP.md) for setting up the remote side
(dedicated user, restricted SSH key, host key pinning).

## Full documentation

- [docs/INSTALL.md](docs/INSTALL.md) -- installing on Linux/Windows, and scheduling with systemd or cron
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) -- full config.json reference and every CLI subcommand
- [docs/SFTP_SETUP.md](docs/SFTP_SETUP.md) -- setting up a remote backup destination over SFTP
- [docs/PROXMOX.md](docs/PROXMOX.md) -- what to (and not to) back up on a Proxmox VE host
- [docs/NEXTCLOUD.md](docs/NEXTCLOUD.md) -- backing up Nextcloud config + database + data
- [docs/RESTORE.md](docs/RESTORE.md) -- restoring a full snapshot, a single file, or a folder
- [docs/DISASTER_RECOVERY.md](docs/DISASTER_RECOVERY.md) -- **read this before you rely on this tool.** Losing the encryption key means losing every backup, permanently.

## How it's laid out

```
haven_backup/
  backends/          local + SFTP storage backends (StorageBackend interface)
  crypto_engine.py   AES-256-GCM, key persistence / passphrase derivation
  storage_engine.py  chunking, hashing, dedup, encrypt/decrypt
  index_engine.py    chunk registry + staging (resumable backups)
  backup_engine.py   scan -> chunk -> store -> commit snapshot
  restore_engine.py  snapshot -> files back on disk
  browser_engine.py  interactive snapshot browser (manual/ad-hoc use)
  health_engine.py   integrity / disk space / incomplete-backup checks
  prune_engine.py    retention policy + garbage collection
  update_engine.py   optional, manual self-update of this installation via git
  cli.py             the `haven-backup` command
```

## Status

This is a personal-infrastructure backup tool, not a widely-audited product.
It's used to back up the author's own home-lab servers. Read
[docs/DISASTER_RECOVERY.md](docs/DISASTER_RECOVERY.md), test a full restore
before you trust it with anything, and keep an independent backup of anything
truly irreplaceable.

## License

MIT -- see [LICENSE](LICENSE).

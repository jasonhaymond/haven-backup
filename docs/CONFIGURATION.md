# Configuration reference

Config lives at `~/.haven_backup/config.json` (created by `haven-backup init`).
Edit it with the `haven-backup config ...` subcommands rather than by hand where
possible, since they validate input and keep the file permissions locked down.

## config.json shape

```json
{
  "backup_paths": ["/etc", "/etc/pve"],
  "exclude_patterns": ["*.log", "*/cache/*"],
  "destination": {
    "type": "local",
    "path": "/mnt/backup-share/myhost"
  },
  "auto_update_enabled": false,
  "update_channel": "main",
  "retention_policy": { "full": 3, "incremental": 7 },
  "last_update_time": null
}
```

For an SFTP destination, `destination` instead looks like:

```json
{
  "type": "sftp",
  "host": "backup.example.com",
  "port": 22,
  "username": "haven",
  "key_path": "/home/haven/.ssh/id_ed25519",
  "remote_path": "/mnt/backups/myhost",
  "auto_add_host_key": false,
  "password": null
}
```

| Field | Meaning |
|---|---|
| `backup_paths` | Files/directories to back up. Directories are walked recursively. |
| `exclude_patterns` | `fnmatch` glob patterns matched against full paths; matching files (and pruned subdirectories) are skipped. |
| `destination.type` | `"local"` or `"sftp"`. |
| `destination.path` | (local only) Repo root -- can be a local disk or a mounted network share. |
| `destination.host/port/username/key_path/password/remote_path/auto_add_host_key` | (sftp only) See [SFTP_SETUP.md](SFTP_SETUP.md). |
| `retention_policy.full` / `.incremental` | How many of each snapshot type `prune` keeps. |
| `auto_update_enabled` | Whether `haven-backup update` runs are checked automatically; the update command itself is always manual to run (`haven-backup update`). Defaults off -- see [update_engine.py](../haven_backup/update_engine.py). |

## CLI reference

```
haven-backup init
    Bootstrap ~/.haven_backup/{config.json,master.key}.

haven-backup backup [--type full|incremental]
    Run a backup. Resumes an interrupted run of the same type if one is staged.

haven-backup snapshots
    List snapshot ids, newest first.

haven-backup restore <snapshot_id> full [--to PATH] [--dry-run]
haven-backup restore <snapshot_id> paths <path> [<path> ...] [--to PATH] [--dry-run]
    Restore everything, or only paths starting with one of the given prefixes.
    Without --to, files are restored to their original absolute paths.

haven-backup browse <snapshot_id>
    Interactive folder browser for ad-hoc restores (not for scripts/cron).

haven-backup healthcheck
    Repo integrity (missing chunks), disk space, incomplete backups.
    Exits non-zero if anything looks wrong -- wire this into monitoring.

haven-backup prune [--dry-run]
    Apply retention_policy, then garbage-collect any now-unreferenced chunk.

haven-backup update [--no-restart]
    Manually git-pull this Haven Backup installation and restart.

haven-backup config show
haven-backup config set-backup-paths <path> [<path> ...]
haven-backup config set-exclude <pattern> [<pattern> ...]
haven-backup config set-retention --full N --incremental N
haven-backup config set-destination local <path>
haven-backup config set-destination sftp --host H --username U --remote-path P
                                          [--port 22] [--key-path PATH] [--auto-add-host-key]
```

## Multiple machines, one destination

Each server runs its own `haven-backup` install and its own encryption key --
keys are never shared or transmitted. Point each machine's `destination` at
its own subdirectory (local mount or `remote_path`) so their repos don't
collide, e.g. `/mnt/backups/proxmox1`, `/mnt/backups/nextcloud1`.

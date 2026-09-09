# Restoring

## List what's available

```bash
haven-backup snapshots
```

Snapshot ids look like `full_20260315020000` or `incremental_20260316020000`
(type + UTC timestamp).

## Restore everything from a snapshot

```bash
# To original absolute paths (overwrites what's currently there):
haven-backup restore full_20260315020000 full

# To a scratch directory instead (always do this first to sanity-check):
haven-backup restore full_20260315020000 full --to /tmp/restore-check
```

With `--to`, each file's original absolute path is recreated under that root
(e.g. `/etc/pve/storage.cfg` restores to `/tmp/restore-check/etc/pve/storage.cfg`)
so files from different original locations never collide.

## Restore specific files or folders

```bash
haven-backup restore full_20260315020000 paths /etc/pve/storage.cfg
haven-backup restore full_20260315020000 paths /etc/pve /etc/network --to /tmp/restore-check
```

Any backed-up path starting with one of the given prefixes is restored.

## Dry run first

```bash
haven-backup restore full_20260315020000 full --dry-run
```

Prints every file that would be restored without touching disk. Always do
this (or restore to `--to /tmp/...`) before restoring over live config on a
production host.

## Browsing interactively

```bash
haven-backup browse full_20260315020000
```

A simple folder browser for finding a specific file inside a snapshot by eye.
Not scriptable -- use `restore paths` directly for anything automated.

## Verify integrity before you need it

```bash
haven-backup healthcheck
```

Checks that every chunk referenced by every snapshot is actually present in
the repo. Run this regularly (it's in the bundled systemd timer), not just
when you're already in the middle of an emergency.

# Disaster recovery -- read this before you rely on Haven Backup

## The encryption key is the whole story

Every chunk is encrypted with AES-256-GCM under one master key, generated
once per machine. **There is no way to decrypt a repo without that key.**
Not a bug to file, not a recovery mode to ask for -- that's what "encrypted"
means. Losing the key means every backup made with it is permanently, and
by design, unrecoverable.

There are two ways the key is derived (see `haven_backup/crypto_engine.py`):

### Option A -- passphrase-derived key (recommended for disaster recovery)

Set `HAVEN_BACKUP_PASSPHRASE` in the environment before Haven Backup runs
(e.g. in the systemd unit's `Environment=` line, or an `EnvironmentFile`).
The key is derived from it via PBKDF2 with a non-secret salt stored next to
where the key file would otherwise be.

- **What you must protect:** the passphrase itself (write it down somewhere
  durable and offline -- a password manager, a printed copy in a safe).
- **Why this is the disaster-recovery-friendly option:** if the server
  hosting Haven Backup is destroyed entirely, you can stand up a fresh
  machine, set the same passphrase, and re-derive the identical key -- there's
  no file that can be lost, because the salt file itself isn't secret (it's
  only there to make the derivation resistant to precomputation, not to add
  entropy you need to protect).

### Option B -- a random key file (`~/.haven_backup/master.key`)

If no passphrase is set, a random 256-bit key is generated once and written
to `~/.haven_backup/master.key` (mode 600).

- **What you must protect:** that exact file. Back it up somewhere
  *independent of the backup repo it protects* -- if your only copy of the
  key lives on the same disk as the server it's encrypting backups for, a
  single disk failure takes out both the backups and the only thing that
  could ever decrypt them.
- Practical options: copy it into a password manager, print/write it down and
  store it physically, or keep an encrypted copy on a separate device.

**Pick one approach per machine and note which one you used somewhere durable
outside the machine itself** (a password manager entry, a runbook) -- "I
think I used a passphrase but I don't remember what it was" is exactly as bad
as losing a key file.

## What losing the destination (not the key) means

If the repo destination is lost (disk failure, remote host gone) but you
still have the key, you've lost the backups but the key itself is still
fine for future backups to a new destination. This is the "normal" failure
mode -- keep the destination on redundant storage, and remember the whole
point of a backup is that the destination is not the only copy of anything.

## Test a real restore before you need one

```bash
haven-backup backup --type full
haven-backup restore <snapshot_id> full --to /tmp/restore-check
diff -r /etc /tmp/restore-check/etc   # or wherever you backed up
```

A backup job that has never been through a successful restore is a belief,
not a fact. Do this once after initial setup, and again after any
significant config change to what's backed up.

## Repository integrity

```bash
haven-backup healthcheck
```

Run this on a schedule (the bundled systemd timer does). It reports any
snapshot referencing a chunk that's no longer present in the repo -- catch
that early, not the day you actually need the restore.

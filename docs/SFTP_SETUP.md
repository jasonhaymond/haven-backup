# Setting up an SFTP backup destination

Haven Backup can push encrypted chunks straight to a remote host over SFTP --
no mount required. This is the natural setup for "backup server pulls in
nothing, every source server pushes out over SSH."

## 1. On the backup destination host

Create a dedicated, restricted account -- don't reuse an existing admin account:

```bash
sudo useradd -m -s /usr/sbin/nologin haven-backup   # nologin: SFTP only, no shell
sudo mkdir -p /mnt/backups
sudo chown haven-backup:haven-backup /mnt/backups
```

Restrict it to SFTP and chroot it to the backup directory, in `/etc/ssh/sshd_config`:

```
Match User haven-backup
    ChrootDirectory /mnt/backups
    ForceCommand internal-sftp
    AllowTcpForwarding no
    X11Forwarding no
```

(Chrooting requires `/mnt/backups` and every directory above it to be owned by
`root` and not group/world-writable; each source machine's own subdirectory
under it, e.g. `/mnt/backups/proxmox1`, can be owned by `haven-backup`.)

```bash
sudo systemctl restart sshd
```

## 2. On each source server

Generate a dedicated key (don't reuse a personal key) and copy it over:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/haven_backup_key -N "" -C "haven-backup@$(hostname)"
ssh-copy-id -i ~/.ssh/haven_backup_key.pub haven-backup@backup.example.com
```

Test it manually once:

```bash
sftp -i ~/.ssh/haven_backup_key haven-backup@backup.example.com
```

The first connection will prompt to trust the host key -- accept it, which adds
it to `~/.ssh/known_hosts`. Haven Backup uses `paramiko`'s system host-key
store (`load_system_host_keys()`) and **rejects unknown host keys by default**,
so do this manual `sftp` connection first rather than passing
`--auto-add-host-key` (which trusts on first use with no verification --
convenient for a quick lab setup, not something you want for a real
destination reachable over the internet).

## 3. Point Haven Backup at it

```bash
haven-backup config set-destination sftp \
  --host backup.example.com \
  --username haven-backup \
  --remote-path /proxmox1 \
  --key-path ~/.ssh/haven_backup_key
```

(`--remote-path` is relative to the chroot, so `/proxmox1` here means
`/mnt/backups/proxmox1` on the destination host.)

```bash
haven-backup backup --type full
haven-backup healthcheck
```

## Notes

- The encryption key never leaves the source machine -- the destination only
  ever stores encrypted `.enc` chunks and JSON snapshot/index metadata with
  paths and chunk hashes, never plaintext or the key itself.
- Prefer a key without a passphrase for unattended cron/systemd runs (an
  encrypted private key would need an agent or an interactive prompt); rely on
  restricting what that key can do (dedicated account, chroot, `nologin`
  shell) rather than a passphrase for its security.
- If the connection drops mid-backup, Haven Backup retries the failing
  operation a few times with backoff before giving up; a fully interrupted run
  resumes cleanly on the next `haven-backup backup` (see `backup_engine.py`).

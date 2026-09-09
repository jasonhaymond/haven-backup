# Installing Haven Backup

## Requirements

- Python 3.9+
- `pip install -e .` from the repo root (installs `cryptography` and `paramiko`,
  and puts a `haven-backup` command on your PATH)

## Linux (typical target: a Proxmox host, Nextcloud host, or any server)

```bash
sudo apt install -y python3 python3-venv git      # Debian/Proxmox VE
git clone https://github.com/jasonhaymond/haven-backup.git /opt/haven-backup
cd /opt/haven-backup
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/haven-backup init
```

Run it as a dedicated, unprivileged user where possible. On a Proxmox host,
root access is required to read some config paths (e.g. `/etc/pve`), so it's
reasonable to run as root there specifically -- see
[PROXMOX.md](PROXMOX.md) for scoping recommendations.

## Windows

```powershell
git clone https://github.com/jasonhaymond/haven-backup.git
cd haven-backup
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\haven-backup init
```

## Configure

```bash
haven-backup config set-backup-paths /etc /etc/pve
haven-backup config set-exclude "*.log" "*/cache/*"
haven-backup config set-retention --full 3 --incremental 7

# Local destination (can be a mounted NFS/SMB/sshfs share):
haven-backup config set-destination local /mnt/backup-share/$(hostname)

# ...or push straight to a remote host over SFTP, no mount needed:
haven-backup config set-destination sftp \
  --host backup.example.com --username haven \
  --remote-path /mnt/backups/$(hostname) --key-path ~/.ssh/id_ed25519
```

Run a backup by hand once to confirm it works end to end before scheduling it:

```bash
haven-backup backup --type full
haven-backup snapshots
haven-backup healthcheck
```

## Scheduling on Linux with systemd (recommended)

Copy the unit + timer templates from [systemd/](../systemd/) (edit `ExecStart`
paths if you didn't install to `/opt/haven-backup`), and enable both pairs:

```bash
sudo cp systemd/haven-backup*.service systemd/haven-backup*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now haven-backup.timer haven-backup-prune.timer
systemctl list-timers 'haven-backup*'      # confirm both are scheduled
journalctl -u haven-backup.service         # check a run's output
```

`haven-backup.timer` runs a full backup daily; `haven-backup-prune.timer`
applies retention weekly. Adjust the `OnCalendar=` lines to taste. Exit codes
matter here: `backup` and `healthcheck` return non-zero on failure, so
systemd (and anything watching `systemctl is-failed haven-backup.service`)
will correctly flag a bad run.

## Scheduling with cron (alternative)

```
# /etc/cron.d/haven-backup
0 2 * * *  root  /opt/haven-backup/.venv/bin/haven-backup backup --type full >> /var/log/haven-backup-cron.log 2>&1
30 3 * * 0 root  /opt/haven-backup/.venv/bin/haven-backup prune >> /var/log/haven-backup-cron.log 2>&1
```

## Before you walk away

Do a full restore to a scratch directory and diff it against the source at
least once, and read [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) about
protecting the encryption key/passphrase -- a perfectly running backup job is
worthless if nothing can ever decrypt its output.

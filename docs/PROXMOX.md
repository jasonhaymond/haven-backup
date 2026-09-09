# Backing up a Proxmox VE host

Haven Backup is for the **host OS and configuration**, not VM/container disk
images. For actual VM/CT backups, use Proxmox's own tooling
(`vzdump`, or ideally a Proxmox Backup Server instance) -- it understands
qemu/LXC snapshots properly; Haven Backup walking a live multi-GB disk image
file byte-by-byte would be slow, wouldn't be crash-consistent, and defeats the
point of content-addressable dedup (VM images churn too much internally to
dedupe well chunk-to-chunk). Use the two together, not one instead of the other.

## What to include

```bash
haven-backup config set-backup-paths \
  /etc/pve \
  /etc/network/interfaces \
  /etc/hosts \
  /etc/hostname \
  /etc/resolv.conf \
  /etc/pve/firewall \
  /root/.ssh \
  /etc/ssh/sshd_config \
  /etc/cron.d /etc/crontab \
  /etc/apt/sources.list /etc/apt/sources.list.d
```

`/etc/pve` is the big one -- it's Proxmox's cluster filesystem (pmxcfs), and
contains VM/CT configs (`qemu-server/`, `lxc/`), storage config
(`storage.cfg`), cluster membership, users/permissions, and firewall rules.
Losing this (without a backup) means manually recreating every VM's
CPU/disk/network definition by hand even if the underlying disk images are
fine.

## What to exclude

```bash
haven-backup config set-exclude \
  "/etc/pve/nodes/*/qemu-server/*.conf.tmp" \
  "*.log"
```

`/etc/pve` is a virtual/in-memory filesystem (backed by a SQLite DB under the
hood) -- it's small and safe to back up in full; don't bother excluding
subdirectories of it.

## Restoring after a host rebuild

1. Reinstall Proxmox VE, join it to the cluster if applicable.
2. Restore `/etc/pve` and the other config paths from the latest snapshot
   (see [RESTORE.md](RESTORE.md)) -- pmxcfs will pick the restored VM/CT
   configs back up.
3. Restore your VM/CT disk images separately, from your `vzdump`/PBS backups.
4. Start the VMs/CTs and confirm they come up with the expected config.

## Cluster nodes

Each node has its own `/etc/pve` view of the same cluster filesystem, so
you technically only need one node's `/etc/pve` backed up for cluster config
-- but back up every node's `/etc/network/interfaces`, SSH host keys, etc.
individually, since those are genuinely per-node.

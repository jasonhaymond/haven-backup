# Integrating with existing borgmatic clients

Haven Backup assumes each client host (Proxmox, Nextcloud, etc.) already runs
`borgmatic` via its own cron/systemd timer. The portal adds two things on top
of that: centralized retention, and an optional "run now" trigger. It does
not replace your client-side borgmatic config -- it works alongside it, with
one important change recommended below.

## Recommended: let the portal own `prune`, not each client

If a client's `borgmatic` config runs `prune` on its own schedule with its
own `keep_*` rules, and the portal *also* runs `borg prune` against the same
repo with the retention policy configured in the portal, the two will
periodically disagree about what to keep -- not dangerous (prune only ever
removes archives outside the keep-rules currently in force), but confusing,
and it means the retention policy shown in the portal isn't actually the
one governing the repo.

Recommended split:

- **Client's `borgmatic.yaml`**: keep `source_directories`, `repositories`,
  `encryption_passphrase` (or `encryption_passphrase_command`), and the
  `create` (and optionally `check`) actions. Remove `prune`'s `keep_*` config,
  or exclude `prune` from the actions borgmatic's own schedule runs (e.g. via
  `borgmatic create` in cron/systemd rather than a bare `borgmatic`, which
  by default runs `prune`+`compact`+`create`+`check`).
- **Portal**: owns retention entirely -- set `keep_daily`/`keep_weekly`/
  `keep_monthly`/`keep_yearly` on the repo in the portal, and let the
  scheduled prune job (or your own "apply retention now" clicks) be the only
  thing invoking `borg prune` against that repo.

Example client-side cron entry that only creates (no client-side prune):

```
0 2 * * *  root  borgmatic --config /etc/borgmatic/config.yaml create --stats
```

## What "backup now" actually runs

`POST /api/hosts/{id}/backup-now` SSHes into the client host and runs exactly:

```
borgmatic --config <borgmatic_config_path> create --stats
```

Deliberately `create` only -- see `backend/app/host_service.py`. It never
invokes the client's full borgmatic action list, so it can't accidentally
trigger a client-side prune even if you haven't gotten around to trimming
that client's config yet.

## borgmatic version note

`create --stats` is standard action-subcommand syntax (borgmatic >= 1.6-ish).
If your client hosts run an older borgmatic without action subcommands,
you'll need to adjust the command built in `host_service.py` to match
(e.g. a bare `borgmatic --config ... --stats` with prune/compact/check
disabled via config instead of via the command line).

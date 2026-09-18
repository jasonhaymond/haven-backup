# Working with a locked-down (restricted) account on the backup server

Many backup servers, once they host more than one thing, give each app/tenant
its own restricted SSH account instead of one shared account with full shell
access -- so a compromised client key can't read or delete anyone else's
data, or run arbitrary commands on the backup server itself. If your backup
host already does this for other apps, Haven Backup should get the same
treatment, not a shared/full-access account carved out just for convenience.

## What "locked down" usually means

The standard Borg-recommended way to restrict an SSH key to only speak the
Borg RPC protocol, scoped to one or more paths, is an `authorized_keys` entry
like:

```
command="borg serve --restrict-to-path /srv/backups/<app>",restrict ssh-ed25519 AAAA... haven-backup@portal
```

- `command="borg serve ..."` -- whatever command the SSH client actually
  asked for is ignored; the server always runs `borg serve` instead. There's
  no shell access with this key, ever.
- `restrict` (OpenSSH >= 7.2) -- turns off port forwarding, agent forwarding,
  X11, and pty allocation, in addition to the `command=` restriction.
- `--restrict-to-path` (repeatable) -- limits `borg serve` itself to only
  serving repos under those paths, even though the SSH-level restriction
  above would otherwise allow the account to run `borg serve` unscoped.

If another app on your backup server already has an account that looks like
this, that's the same pattern -- Haven Backup fits into it, it doesn't need
something different.

## Setting this up for Haven Backup

### Option 1: a dedicated account for Haven Backup (recommended if other apps get their own)

1. On the backup server, create the account the same way you created the
   others (adjust to your actual convention -- system user, no login shell):
   ```bash
   sudo adduser --disabled-password --gecos "" haven-backup
   sudo mkdir -p /srv/backups/haven-backup /home/haven-backup/.ssh
   sudo chown haven-backup:haven-backup /srv/backups/haven-backup /home/haven-backup/.ssh
   sudo chmod 700 /home/haven-backup/.ssh
   ```
2. Generate the key **in Haven Backup**, per the walkthrough on the
   SSH Credentials page in the UI
   (`ssh-keygen -t ed25519 -f ~/.ssh/haven_<name> -N "" -C "haven-backup"`),
   then add its **public** key to that account's `authorized_keys` with the
   restriction -- don't use `ssh-copy-id` here, that would grant unrestricted
   access:
   ```bash
   sudo -u haven-backup bash -c 'cat >> ~/.ssh/authorized_keys' <<'EOF'
   command="borg serve --restrict-to-path /srv/backups/haven-backup",restrict ssh-ed25519 AAAA... haven-backup@portal
   EOF
   sudo chmod 600 /home/haven-backup/.ssh/authorized_keys
   ```
3. In Haven Backup's **SSH credential**, use `username: haven-backup`
   against this host with that private key.
4. Every repo you add in Haven Backup must live under a path listed in
   `--restrict-to-path`. Need more than one directory? Repeat the flag,
   space-separated, on the same `command=` line -- don't grant a parent
   directory "to be safe"; list exactly the paths Haven Backup needs.

### Option 2: reuse an existing per-client restricted account

If the client host that creates a repo's archives already has its own
restricted account+key on the backup server (common if clients were set up
before Haven Backup existed), you can point the same SSH credential fields
in Haven Backup at that existing account instead of creating a new one --
Haven Backup doesn't need a unique identity per repo, only *an* identity
that's allowed to reach that repo's path.

Tradeoff: this puts that client's own key material inside the portal's
database too (see [SECURITY.md](SECURITY.md)'s "master key" framing) --
a leak of the portal's data now also exposes that client's restricted
account, not just a portal-only one. Option 1 (a dedicated key) is still
the better default; reuse an existing account only when it's already broad
enough that this doesn't meaningfully add exposure.

## Changing the restricted path later

The setup command above uses `>>`, which only **appends** a line -- running
it again with a different path doesn't replace the restriction, it leaves
two separate `command=...` lines for the same key (confusing, and the
second one wins depending on how you added it, which isn't something to
rely on). To actually change which path(s) a key is restricted to, edit the
existing line in place instead.

**Edit directly with a text editor:**

```bash
sudo -u haven-backup nano /home/haven-backup/.ssh/authorized_keys
```

Find the line and change the path(s) inside `--restrict-to-path`. For more
than one path, repeat the flag, space-separated, inside the same quoted
`command="..."` string:

```
command="borg serve --restrict-to-path /srv/backups/haven-backup --restrict-to-path /srv/backups/another-repo",restrict ssh-ed25519 AAAA... haven-backup@portal
```

**Or script it** (handy if you're doing this repeatedly, or from a deploy
script) with `sed`:

```bash
sudo -u haven-backup sed -i \
  's#--restrict-to-path [^"]*#--restrict-to-path /srv/backups/new-path#' \
  /home/haven-backup/.ssh/authorized_keys
```

Adjust the replacement pattern if you're going from one path to several.

**After editing:**

```bash
sudo chmod 600 /home/haven-backup/.ssh/authorized_keys   # in case the editor reset it
cat /home/haven-backup/.ssh/authorized_keys                # sanity-check the result
```

No service restart needed -- `sshd` re-reads `authorized_keys` on every new
connection, so the change takes effect on the *next* SSH attempt. Haven
Backup opens a fresh SSH connection per `borg` invocation rather than
holding one open, so in practice the new restriction applies immediately.

Re-run the verification command below before trusting the portal against
the new path again. And if you're moving a repo to a new path, update the
repo's `ssh://` URL on the **Repositories** page in Haven Backup to match --
the `authorized_keys` restriction and the portal's stored URL both have to
agree, or you'll get an authentication/permission error even though each
half looks correct on its own.

## The append-only trap: retention needs delete rights

A hardened backup-server setup often adds `--append-only` to the same
`borg serve` restriction, specifically so a compromised *client* key can
create new archives but never delete/prune old ones (ransomware
resistance):

```
command="borg serve --restrict-to-path /srv/backups/haven-backup --append-only",restrict ssh-ed25519 ...
```

**Haven Backup's own retention (`borg prune`, and `compact`) needs delete
rights -- it will fail against an append-only account** with a permission
error from `borg serve`, not a bug in the portal. This is a real tradeoff to
decide per repo, not a misconfiguration to "fix":

- If ransomware-resistance for this repo matters more than the portal's
  automatic/on-demand pruning: leave the account append-only, and don't set
  a retention policy on that repo in Haven Backup (or expect "Apply
  retention now" to fail every time). Prune this repo out-of-band instead --
  locally on the backup server, where a trusted operator, not a remote key,
  actually has delete rights.
- If you want the portal to manage retention for this repo: that repo's
  account can't be append-only. Use a **separate** restricted account
  (still `--restrict-to-path`-scoped, just without `--append-only`)
  dedicated to the portal, distinct from whatever append-only account the
  client itself uses to create archives. This keeps the client's own key
  ransomware-resistant while still letting the portal -- a separate trust
  boundary from any one client -- own pruning.

Decide this up front per repo. Don't discover it by watching prune runs fail
in the portal's run history.

## Verifying the restriction actually works before pasting the key into the portal

Test with `borg` itself, not plain `ssh` -- a restricted account behind
`command="borg serve ..."` won't respond to something like
`ssh user@host whoami`; it starts speaking the Borg protocol at you instead
and just hangs (expected; Ctrl-C out of it):

```bash
BORG_RSH="ssh -i ~/.ssh/haven_<name>" \
  borg info ssh://haven-backup@backup-host/./srv/backups/haven-backup/some-repo
```

If this returns repo info, the restricted account is wired up correctly, and
Haven Backup's own `info`/`list`/`prune`/`check` calls (which speak the same
protocol) will work identically. If it hangs or errors, fix it here first --
pasting an untested credential into the portal just moves the same failure
into a run-history entry instead of your terminal.

## What Haven Backup does *not* need on the backup server

- No shell access, ever -- `command="borg serve ..."` covers everything the
  portal does against a repo (info, list, prune, check).
- No sudo/root.
- No access to paths outside `--restrict-to-path`.

## Client hosts ("backup now") are a separate, unrelated account

Everything above is about the **backup/repo host** the portal talks to
directly over `borg`'s own SSH transport. The credential used for "backup
now" -- SSHing into a **client** host to run `borgmatic create` -- is a
different machine, a different concern, and already covered in
[SECURITY.md](SECURITY.md#ssh-keys-used-for-client-backup-now): restrict it
via `command="borgmatic --config /etc/borgmatic/config.yaml create --stats"`
if you want to be equally strict there. The two restrictions don't interact
with each other.

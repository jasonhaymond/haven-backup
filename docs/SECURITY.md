# Security model

This portal, once configured, holds SSH private keys to your backup host and
possibly every client host, plus every Borg repo's passphrase. Treat its data
directory (and whoever can reach its web UI) accordingly -- this is
effectively a master key to your entire backup estate.

## What's encrypted at rest, and what that does (and doesn't) protect

SSH private keys and Borg passphrases are encrypted with AES-256-GCM
(`backend/app/crypto.py`) before being stored in the SQLite database, using a
key file (`backend/data/secret.key` by default) generated on first run.

This protects: a copy of the database file alone (e.g. from a stolen/leaked
backup of the portal's own data, or a disk that outlives the host) without
the accompanying key file.

This does **not** protect: anyone with access to a *running, unlocked*
instance of the portal (its own database + secret key together, e.g. root on
its host, or its entire `data/` directory) -- they can decrypt everything the
portal manages, the same as anyone who could read `~/.ssh/id_rsa` on a
machine they've already compromised. There's no separate "vault unlock"
step; this is a config-management tool, not a secrets vault like Vault/age.

Back up `backend/data/` (or the `haven_data` Docker volume) like you would
any other credential store: encrypted, access-controlled, and separately
from whatever it's protecting. See [BACKUP.md](BACKUP.md) for the actual
(tested) commands.

## Login

Single/multi-user username+password with bcrypt hashing, and a signed
(itsdangerous), httpOnly session cookie (`backend/app/security.py`) -- no
JWT library, no external session store.

- **No self-service "forgot password."** Deliberately -- that would mean
  accepting some unauthenticated request as proof of identity, on a tool
  that holds SSH keys and Borg passphrases. If you're locked out, reset it
  from the host/container instead:
  ```
  docker compose exec backend python scripts/reset_password.py <username>
  docker compose exec backend python scripts/reset_password.py <username> --generate
  ```
  The `--generate` form prints a strong random password once -- save it
  immediately, it cannot be shown again. See
  `backend/scripts/reset_password.py`'s own docstring, and
  `create_user.py` alongside it for adding a second admin instead.

- **Rate limiting**: `/api/auth/login` and `/api/auth/setup` are limited to
  `HAVEN_LOGIN_RATE_LIMIT_ATTEMPTS` (default 10) attempts per
  `HAVEN_LOGIN_RATE_LIMIT_WINDOW_SECONDS` (default 300) per client IP, via an
  in-process in-memory limiter (`backend/app/rate_limit.py`) -- no external
  store needed at this scale, but it resets on restart and is per-process
  (irrelevant here since this runs as a single backend process).
- **No 2FA.** If you expose this beyond a trusted network, put it behind
  something that adds it (a reverse proxy with its own auth, a VPN/Tailscale).
- **Session cookie `Secure` flag** (`HAVEN_COOKIE_SECURE`, default `false` in
  the bundled Docker Compose stack): a real browser refuses to even store a
  cookie marked `Secure` over plain HTTP, which is what the bundled `web`
  container serves by default -- so it defaults off there. Once you put a
  real TLS-terminating reverse proxy in front (see
  [DEPLOYMENT.md](DEPLOYMENT.md)), set this to `true` and restart. Verified
  directly with a headless browser during development: login silently failed
  to persist a session with this on over plain HTTP, and worked correctly
  once off (or once real TLS was in front with it on).

## Update-available check (outbound call to GitHub)

`GET /api/version` calls GitHub's public tags API
(`api.github.com/repos/<owner>/<repo>/tags`) to show whether a newer release
exists -- no auth, no request body, nothing project-specific sent beyond
"what tags does this public repo have." Still opt-out rather than silently
unconditional, because this is a tool that holds SSH keys and Borg
passphrases and an outbound network call from it deserves a kill switch:
set `HAVEN_UPDATE_CHECK_ENABLED=false` for fully offline operation. Result
is cached for an hour; a failed/blocked call degrades to "no update info"
rather than erroring.

**This only shows visibility, never triggers anything.** The backend
container is a built image with no git checkout and no Docker socket
access -- it cannot `git pull`, rebuild, or restart itself. Giving it a
`docker.sock` mount so a UI button *could* trigger `scripts/update.sh` on
the host was considered and rejected: that passthrough effectively grants
the container root on the host (anything with Docker socket access can
launch a privileged container), which is a disproportionate attack surface
increase for a single-operator convenience feature on a tool that already
holds the keys to your backup infrastructure. The actual update stays an
explicit `./scripts/update.sh` run on the host -- see
[DEPLOYMENT.md](DEPLOYMENT.md#updating-and-rolling-back).

## SSH host key verification

- **Repo access** (`borg` shelling out via `BORG_RSH`): defaults to
  `StrictHostKeyChecking=accept-new` -- trusts a host's key the first time,
  rejects if it later changes. Pre-populate the portal container's
  `known_hosts` yourself (mount one in, or run `ssh-keyscan` as part of image
  build/entrypoint) if you want strict verification from the very first
  connection.
- **Client access** (`paramiko`, for "backup now"): defaults to
  `AutoAddPolicy` (trust-on-first-use). For anything internet-reachable,
  replace this with a pinned host key: pre-populate
  `~/.ssh/known_hosts` in the portal's container/host for each client, and
  change `ssh_exec.py`'s `set_missing_host_key_policy` to
  `paramiko.RejectPolicy()`.

## SSH keys used for client "backup now"

Give each client host a dedicated key (not a personal/admin key), scoped via
`authorized_keys` `command=` restriction if you want to be strict about
what that key can run beyond `borgmatic create` -- the portal only ever
sends that one command, but a leaked key with no `command=` restriction on
the client could be used for anything.

## Passphrases and private keys in transit to the running processes

`borg`'s passphrase is passed via the `BORG_PASSPHRASE` environment variable
to a locally-spawned `borg` subprocess (not visible to other users' `ps`
output on a properly multi-user-isolated host, though environment variables
of a process are visible to root/the same user). The SSH private key used
for a given `borg` invocation is written to a temp file
(`backend/data/ssh_keys/`) with `0600` permissions immediately before use and
deleted immediately after (see `borg_runner._materialize_key`) -- it exists
on disk only for the duration of that one command.

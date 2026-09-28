#!/usr/bin/env bash
# Haven Backup client enrollment. Generated per host from the portal's Client Hosts page:
#
#   curl -fsSL https://<portal>/api/enroll/install.sh | sudo bash -s -- --portal https://<portal> --token <token>
#
# What it does, in order (full manual equivalent: docs/CLIENT_ENROLLMENT.md):
#   1. checks this is a root shell on a Debian-family system with systemd
#   2. installs borgbackup + borgmatic from apt (skipped if already present)
#   3. creates this host's own SSH key for reaching the backup server
#   4. claims the token -- the portal registers this host + its repo and returns its config
#   5. writes /etc/borgmatic/haven.yaml, a systemd service + timer, and a restricted
#      authorized_keys entry so the portal's "Backup now" can run `borgmatic create` only
#   6. prints the one line you paste on the backup server, waits until it's in place,
#      initializes the repo, and starts the first backup
#
# Re-running with no --token resumes from step 6 (e.g. after Ctrl+C while waiting).
# Flags: --dry-run (checks only, changes nothing), --uninstall, --allow-http, --no-first-backup,
#        --wait-minutes N (default 30), --yes (skip the confirmation prompt).
set -euo pipefail

# Everything runs inside main() so bash has read the whole script before executing any
# of it -- under `curl | bash` a command reading stdin could otherwise eat the rest.
main() {
STATE_DIR=/etc/haven-backup
STATE_FILE=$STATE_DIR/enrollment.env
UNIT=haven-backup
PORTAL="" TOKEN="" DRY_RUN=0 UNINSTALL=0 ALLOW_HTTP=0 FIRST_BACKUP=1 WAIT_MINUTES=30 ASSUME_YES=0

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --portal) PORTAL="${2:-}"; shift 2 ;;
    --token) TOKEN="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --allow-http) ALLOW_HTTP=1; shift ;;
    --no-first-backup) FIRST_BACKUP=0; shift ;;
    --wait-minutes) WAIT_MINUTES="${2:-}"; shift 2 ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) echo "Usage: install.sh --portal <url> --token <token> [--dry-run] [--allow-http] [--no-first-backup] [--wait-minutes N] [--yes] | --uninstall"; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done
PORTAL="${PORTAL%/}"

# stdin is the script itself under `curl | bash`, so prompts read the terminal directly.
confirm() {
  [ "$ASSUME_YES" = 1 ] && return 0
  # -r /dev/tty is true even with no controlling terminal; only opening it proves one exists.
  if (exec </dev/tty) 2>/dev/null; then
    local reply
    read -r -p "$1 [y/N]: " reply </dev/tty || return 1
    [[ "$reply" =~ ^[Yy]$ ]]
  else
    die "No terminal to confirm on -- re-run with --yes to proceed non-interactively"
  fi
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
if [ "$UNINSTALL" = 1 ]; then
  [ "$(id -u)" = 0 ] || die "Run as root (sudo)."
  say "Removing Haven Backup client setup from this host (the repo and its archives on the backup server are NOT touched)"
  confirm "Continue?" || exit 1
  systemctl disable --now "$UNIT.timer" 2>/dev/null || true
  rm -f "/etc/systemd/system/$UNIT.service" "/etc/systemd/system/$UNIT.timer"
  systemctl daemon-reload 2>/dev/null || true
  if [ -f /root/.ssh/authorized_keys ]; then
    sed -i '/haven-backup-portal@/d' /root/.ssh/authorized_keys
  fi
  rm -f /etc/borgmatic/haven.yaml
  rm -rf "$STATE_DIR"
  ok "Removed. Left in place: borg/borgmatic packages and /root/.ssh/haven_borg_ed25519 (delete by hand if unwanted)."
  echo "Also remove this host's line from the backup server's authorized_keys, and the host/repo in the portal."
  exit 0
fi

# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------
say "Checking this system"
[ "$(id -u)" = 0 ] || die "Run as root: pipe into 'sudo bash', not plain 'bash'."
command -v apt-get >/dev/null 2>&1 || die "Only Debian/Ubuntu/Proxmox (apt) are supported so far. See docs/CLIENT_ENROLLMENT.md for the manual steps on other systems."
[ -d /run/systemd/system ] || die "systemd isn't running here (needed for the backup timer). See docs/CLIENT_ENROLLMENT.md for a cron-based manual setup."
command -v curl >/dev/null 2>&1 || die "curl is required."
command -v ssh-keygen >/dev/null 2>&1 || die "ssh-keygen is required (apt-get install openssh-client)."
. /etc/os-release 2>/dev/null && ok "OS: ${PRETTY_NAME:-unknown}"

RESUME=0
if [ -z "$TOKEN" ]; then
  [ -f "$STATE_FILE" ] || die "No --token given and no previous enrollment to resume. Generate an install command in the portal (Client Hosts -> Enroll a host)."
  RESUME=1
  ok "Resuming the enrollment recorded in $STATE_FILE"
else
  [ -n "$PORTAL" ] || die "--portal <url> is required with --token"
  case "$PORTAL" in
    https://*) ;;
    http://*) [ "$ALLOW_HTTP" = 1 ] || die "Portal URL is plain http -- the token and the repo passphrase would cross the network unencrypted. Use the portal's https URL, or add --allow-http on a trusted LAN only." ;;
    *) die "--portal must be an http(s) URL" ;;
  esac
  if [ -f "$STATE_FILE" ]; then
    die "This host is already enrolled ($STATE_FILE exists). Run with --uninstall first to re-enroll, or with no --token to resume."
  fi
  if [ -f /etc/borgmatic/haven.yaml ]; then
    die "/etc/borgmatic/haven.yaml already exists but $STATE_FILE doesn't -- refusing to overwrite it. Move it aside first."
  fi
  if command -v sshd >/dev/null 2>&1; then
    prl=$(sshd -T 2>/dev/null | awk '/^permitrootlogin/ {print $2}') || true
    if [ "${prl:-}" = "no" ]; then
      warn "sshd has PermitRootLogin no -- scheduled backups will work, but the portal's \"Backup now\" button won't. Set it to 'prohibit-password' (keys only) to allow it."
    fi
  else
    warn "No SSH server installed -- scheduled backups will work, but the portal's \"Backup now\" button won't until openssh-server is installed."
  fi
fi

if [ "$DRY_RUN" = 1 ]; then
  ok "Dry run: preflight passed. Would now install borgbackup/borgmatic (if missing), create /root/.ssh/haven_borg_ed25519, claim the token, and write /etc/borgmatic/haven.yaml + /etc/systemd/system/$UNIT.{service,timer}. Nothing was changed."
  exit 0
fi

if [ "$RESUME" = 0 ]; then
  echo
  echo "This will install borgbackup + borgmatic, create an SSH key, register this host with"
  echo "  $PORTAL"
  echo "and set up a scheduled backup. The install command's token can only be used once."
  confirm "Continue?" || exit 1

  # -------------------------------------------------------------------------
  # 2. Packages
  # -------------------------------------------------------------------------
  if command -v borg >/dev/null 2>&1 && command -v borgmatic >/dev/null 2>&1; then
    ok "borg and borgmatic already installed"
  else
    say "Installing borgbackup and borgmatic from apt"
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq borgbackup borgmatic >/dev/null
  fi
  BORG_VERSION=$(borg --version 2>/dev/null | awk '{print $2}')
  case "$BORG_VERSION" in
    1.*) ok "borg $BORG_VERSION" ;;
    *) die "borg $BORG_VERSION found -- Haven Backup targets Borg 1.x (see docs/BORG_COMPATIBILITY.md)" ;;
  esac
  BORGMATIC_PATH=$(command -v borgmatic)
  BORGMATIC_VERSION=$(borgmatic --version 2>/dev/null | tail -n1)
  ok "borgmatic $BORGMATIC_VERSION at $BORGMATIC_PATH"
  command -v python3 >/dev/null 2>&1 || die "python3 missing (it's a borgmatic dependency, so this is unexpected)"

  # -------------------------------------------------------------------------
  # 3. This host's key for the backup server
  # -------------------------------------------------------------------------
  KEY=/root/.ssh/haven_borg_ed25519
  install -d -m 700 /root/.ssh
  if [ -f "$KEY" ]; then
    ok "Reusing existing $KEY"
  else
    ssh-keygen -q -t ed25519 -N "" -C "haven-client@$(hostname)" -f "$KEY"
    ok "Created $KEY"
  fi

  # -------------------------------------------------------------------------
  # 4. Claim
  # -------------------------------------------------------------------------
  say "Registering with the portal"
  WORK=$(mktemp -d)
  chmod 700 "$WORK"
  trap 'rm -rf "$WORK"' EXIT
  python3 - "$TOKEN" "$(hostname -f 2>/dev/null || hostname)" "$(cat "$KEY.pub")" "$BORGMATIC_VERSION" "$BORGMATIC_PATH" >"$WORK/req.json" <<'PY'
import json, sys
t, h, k, v, p = sys.argv[1:6]
print(json.dumps({"token": t, "hostname": h, "client_public_key": k, "borgmatic_version": v, "borgmatic_path": p}))
PY
  HTTP_CODE=$(curl -sS -o "$WORK/resp.json" -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
    --data-binary @"$WORK/req.json" "$PORTAL/api/enroll/claim") || die "Could not reach $PORTAL"
  if [ "$HTTP_CODE" != 200 ]; then
    detail=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("detail"))' "$WORK/resp.json" 2>/dev/null || cat "$WORK/resp.json")
    die "Portal refused the enrollment (HTTP $HTTP_CODE): $detail"
  fi
  ok "Registered"

  # -------------------------------------------------------------------------
  # 5. Write config, units, and the portal's restricted key
  # -------------------------------------------------------------------------
  say "Writing configuration"
  install -d -m 700 /etc/borgmatic "$STATE_DIR"
  python3 - "$WORK/resp.json" "$STATE_FILE" <<'PY'
import json, os, shlex, sys
r = json.load(open(sys.argv[1]))

def write(path, content, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    os.chmod(path, mode)

write(r["borgmatic_config_path"], r["borgmatic_config"], 0o600)
unit = r["systemd_unit_name"]
write(f"/etc/systemd/system/{unit}.service", r["systemd_service"], 0o644)
write(f"/etc/systemd/system/{unit}.timer", r["systemd_timer"], 0o644)

ak = "/root/.ssh/authorized_keys"
existing = open(ak).read() if os.path.exists(ak) else ""
line = r["portal_authorized_keys_line"]
if line not in existing:
    with open(ak, "a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(line + "\n")
os.chmod(ak, 0o600)

state = {
    "HAVEN_NAME": r["name"],
    "HAVEN_REPO": r["repo_url"],
    "HAVEN_KEY": r["client_key_path"],
    "HAVEN_CONFIG": r["borgmatic_config_path"],
    "HAVEN_BACKUP_ACCOUNT": r["backup_server_account"],
    "HAVEN_BACKUP_LINE": r["backup_server_line"],
    "HAVEN_PASSPHRASE": r["passphrase"],
}
write(sys.argv[2], "".join(f"{k}={shlex.quote(v)}\n" for k, v in state.items()), 0o600)
PY
  ok "Wrote /etc/borgmatic/haven.yaml, /etc/systemd/system/$UNIT.{service,timer}, and the portal's entry in /root/.ssh/authorized_keys"
  systemctl daemon-reload
  systemd-analyze verify "/etc/systemd/system/$UNIT.timer" >/dev/null 2>&1 || warn "systemd-analyze reported an issue with $UNIT.timer -- check 'systemctl status $UNIT.timer'"
  systemctl enable --now "$UNIT.timer" >/dev/null
  ok "Timer enabled: $(systemctl show -p NextElapseUSecRealtime --value "$UNIT.timer" 2>/dev/null || echo 'see systemctl list-timers')"
fi

# ---------------------------------------------------------------------------
# 6. Backup server access, repo init, first backup
# ---------------------------------------------------------------------------
# shellcheck disable=SC1090
. "$STATE_FILE"
export BORG_PASSPHRASE="$HAVEN_PASSPHRASE"
export BORG_RSH="ssh -i $HAVEN_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"

probe() { borg info "$HAVEN_REPO" >"$STATE_DIR/probe.log" 2>&1; }

echo
say "One manual step: allow this host onto the backup server"
cat <<EOF

On the backup server, as root, append this ONE line to the authorized_keys of
the account ${HAVEN_BACKUP_ACCOUNT%%@*} (on ${HAVEN_BACKUP_ACCOUNT#*@}):

$HAVEN_BACKUP_LINE

For example:
  sudo -u ${HAVEN_BACKUP_ACCOUNT%%@*} tee -a ~${HAVEN_BACKUP_ACCOUNT%%@*}/.ssh/authorized_keys >/dev/null <<'KEY'
$HAVEN_BACKUP_LINE
KEY

(The portal shows the same line on its Client Hosts page.) It restricts this host
to 'borg serve' on its own repository only -- no shell, no other repos.

EOF
say "Waiting for access (checking every 15s for up to $WAIT_MINUTES minutes; Ctrl+C is safe -- re-run with no arguments to resume)"

deadline=$(( $(date +%s) + WAIT_MINUTES * 60 ))
state=""
while :; do
  if probe; then state=exists; break; fi
  if grep -qiE 'does not exist|is not a valid repository' "$STATE_DIR/probe.log"; then state=missing; break; fi
  if grep -qi 'passphrase supplied in BORG_PASSPHRASE' "$STATE_DIR/probe.log"; then
    die "A repository already exists at $HAVEN_REPO with a different passphrase -- refusing to touch it. Details: $STATE_DIR/probe.log"
  fi
  [ "$(date +%s)" -lt "$deadline" ] || die "Still no access after $WAIT_MINUTES minutes. Last error: $(tail -n 3 "$STATE_DIR/probe.log"). Re-run with no arguments to keep waiting."
  sleep 15
done
ok "Backup server access confirmed"

if [ "$state" = missing ]; then
  say "Initializing repository $HAVEN_REPO"
  borg init --encryption=repokey-blake2 "$HAVEN_REPO"
  ok "Repository created (encryption key is stored in the repo, protected by the passphrase the portal holds)"
else
  ok "Repository already initialized"
fi

if [ "$FIRST_BACKUP" = 1 ]; then
  systemctl start --no-block "$UNIT.service"
  ok "First backup started in the background -- follow it with: journalctl -fu $UNIT.service"
fi

echo
ok "Done. '$HAVEN_NAME' should show as healthy on the portal's dashboard after the first backup finishes and the next status refresh (or click Refresh now on its repo)."
echo "Record the repo passphrase somewhere safe outside the portal too -- without it the archives can't be read:"
echo "  sudo grep encryption_passphrase $HAVEN_CONFIG"
}

main "$@"

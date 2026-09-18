#!/usr/bin/env bash
# Interactive, idempotent setup for the Docker Compose deployment.
# Safe to re-run: it offers your existing .env values as defaults and asks
# before overwriting anything. See docs/DEPLOYMENT.md for what this automates
# and what it deliberately doesn't (system/firewall/reverse-proxy config).
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env"

echo "Haven Backup Portal setup"
echo "=========================="
echo

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed. Install it first: https://docs.docker.com/engine/install/" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' (the v2 plugin) is not available. Install the Docker Compose plugin." >&2
  exit 1
fi
echo "[ok] Docker + Docker Compose found."

declare -A existing
if [ -f "$ENV_FILE" ]; then
  echo "[info] Existing $ENV_FILE found -- its values are offered below as defaults."
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    existing["$key"]="$value"
  done < "$ENV_FILE"
fi

prompt() {
  local var_name="$1" prompt_text="$2" default_value="$3"
  local current="${existing[$var_name]:-$default_value}"
  read -r -p "$prompt_text [$current]: " input
  echo "${input:-$current}"
}

WEB_PORT=$(prompt WEB_PORT "Host port for the web UI" "8080")

if command -v lsof >/dev/null 2>&1 && [ -z "${existing[WEB_PORT]:-}" ]; then
  if lsof -iTCP:"$WEB_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[warn] Something is already listening on port $WEB_PORT. Pick a different port unless that's expected."
  fi
fi

HAVEN_NOTIFICATION_WEBHOOK_URL=$(prompt HAVEN_NOTIFICATION_WEBHOOK_URL "Notification webhook URL (blank to disable)" "")
HAVEN_STATUS_REFRESH_MINUTES=$(prompt HAVEN_STATUS_REFRESH_MINUTES "Status refresh interval, minutes" "30")
HAVEN_PRUNE_INTERVAL_HOURS=$(prompt HAVEN_PRUNE_INTERVAL_HOURS "Scheduled prune interval, hours" "24")
HAVEN_COOKIE_SECURE=$(prompt HAVEN_COOKIE_SECURE "Mark the session cookie Secure -- only set true once a real TLS proxy is in front of WEB_PORT, a browser won't store it over plain http otherwise" "false")

echo
if [ -f "$ENV_FILE" ]; then
  read -r -p "$ENV_FILE already exists. Overwrite it with these values? [y/N]: " confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Left $ENV_FILE untouched."
    exit 0
  fi
fi

cat > "$ENV_FILE" <<EOF
WEB_PORT=$WEB_PORT
HAVEN_NOTIFICATION_WEBHOOK_URL=$HAVEN_NOTIFICATION_WEBHOOK_URL
HAVEN_STATUS_REFRESH_MINUTES=$HAVEN_STATUS_REFRESH_MINUTES
HAVEN_PRUNE_INTERVAL_HOURS=$HAVEN_PRUNE_INTERVAL_HOURS
HAVEN_COOKIE_SECURE=$HAVEN_COOKIE_SECURE
EOF
echo "[ok] Wrote $ENV_FILE"
echo

read -r -p "Build and start the stack now with 'docker compose up -d --build'? [Y/n]: " start_now
if [[ ! "$start_now" =~ ^[Nn]$ ]]; then
  docker compose up -d --build
  echo
  echo "Started. Open http://localhost:$WEB_PORT to create the first admin account."
else
  echo "Not starting automatically -- run: docker compose up -d --build"
fi

cat <<'EOF'

Reminder -- this script only wrote .env and (optionally) started the stack.
It deliberately does NOT touch firewall rules or your reverse proxy/TLS
setup -- see "Put it behind your own reverse proxy" in docs/DEPLOYMENT.md
for the manual steps to expose this safely beyond a trusted network.
EOF

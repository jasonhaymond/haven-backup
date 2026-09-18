#!/usr/bin/env bash
# Update (or roll back) the deployed Haven Backup portal.
#
# Usage:
#   scripts/update.sh            # deploy the latest commit on the current branch
#   scripts/update.sh v0.2.0     # deploy/roll back to that exact tagged version
#
# This only ever rolls the CODE forward or back. If the version you're
# targeting expects a different database schema/state than what's currently
# running, restoring the database to match is a separate, deliberate,
# NON-automatic step -- see docs/BACKUP.md. Restoring a snapshot discards
# everything written since it was taken; this script will never do that for
# you implicitly.
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-}"

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: uncommitted local changes present. Commit, stash, or discard them before updating." >&2
  git status --short >&2
  exit 1
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
WEB_PORT="${WEB_PORT:-8080}"

echo "Fetching..."
git fetch --tags origin

if [ -n "$TARGET" ]; then
  if ! git rev-parse "refs/tags/$TARGET" >/dev/null 2>&1; then
    echo "ERROR: tag '$TARGET' not found. Available tags:" >&2
    git tag --list 'v*' --sort=-v:refname >&2
    exit 1
  fi

  cat <<EOF

NOTE: this rolls back CODE ONLY. If $TARGET expects a different database
schema/state than what's currently running, restoring the database to match
is a SEPARATE, MANUAL step -- see docs/BACKUP.md. Restoring a snapshot
discards everything written since it was taken; this script will not do
that for you.

EOF
  read -r -p "Continue with code-only rollback to $TARGET? [y/N]: " confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
  fi
  echo "Checking out $TARGET..."
  git checkout "refs/tags/$TARGET"
else
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
  echo "Deploying latest on $BRANCH..."
  git pull --ff-only origin "$BRANCH"
fi

echo
echo "Taking a pre-restart snapshot of the portal's own data (independent of"
echo "any scheduled backup elsewhere) -- restore procedure in docs/BACKUP.md."
PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/_/g')
VOLUME_NAME="${PROJECT_NAME}_haven_data"
mkdir -p backups

if docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
  # Query the OLD (still-running, not-yet-rebuilt) container for the version actually
  # stamped in its database -- not the git tree, which has already moved by this point.
  RUNNING_VERSION=$(docker compose exec -T backend python scripts/db_version.py 2>/dev/null | tr -d '\r' || echo "unknown")
  VERSION_LABEL="v${RUNNING_VERSION}"
  [ "$RUNNING_VERSION" = "unknown" ] && VERSION_LABEL="unknown-version"
  docker compose stop backend 2>&1 || true
  MSYS2_ARG_CONV_EXCL="*" docker run --rm \
    -v "$VOLUME_NAME:/data" \
    -v "$(pwd)/backups:/backup" \
    alpine tar czf "/backup/haven-data-${VERSION_LABEL}-$(date +%Y%m%d-%H%M%S).tar.gz" -C /data .
  echo "[ok] Snapshot written to backups/ (labeled ${VERSION_LABEL})"
else
  echo "[info] Volume '$VOLUME_NAME' not found (nothing running yet, or a different"
  echo "       COMPOSE_PROJECT_NAME) -- skipping snapshot. Check 'docker volume ls' if unexpected."
fi

echo
echo "Building and restarting..."
docker compose up -d --build

echo
echo "Waiting for the health check to pass..."
for _ in $(seq 1 30); do
  if response=$(curl -sf "http://localhost:${WEB_PORT}/api/health" 2>/dev/null); then
    echo "Healthy: $response"
    echo "Update complete."
    exit 0
  fi
  sleep 2
done

echo "ERROR: health check did not succeed within 60s of restarting. Check logs:" >&2
echo "  docker compose logs -f backend" >&2
exit 1

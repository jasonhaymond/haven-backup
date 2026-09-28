#!/usr/bin/env bash
# One-line installer for the Haven Backup portal itself:
#
#   curl -fsSL https://raw.githubusercontent.com/jasonhaymond/haven-backup/master/scripts/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --version v1.0.0 --dir /opt/haven-backup
#
# Clones the repo and hands off to scripts/setup.sh -- the same end state as the manual
# walkthrough in docs/DEPLOYMENT.md. It never installs system packages or touches
# firewall/reverse-proxy config: Docker and git must already be there (see that doc).
set -euo pipefail

# Everything runs inside main() so bash has read the whole script before executing any
# of it -- under `curl | bash` a command reading stdin could otherwise eat the rest.
main() {
  local repo_url="https://github.com/jasonhaymond/haven-backup.git"
  local dir="$HOME/haven-backup"
  local version=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --dir) dir="${2:-}"; shift 2 ;;
      --version) version="${2:-}"; shift 2 ;;
      --repo) repo_url="${2:-}"; shift 2 ;;
      -h|--help) echo "Usage: install.sh [--dir <path>] [--version <tag>] [--repo <git url>]"; exit 0 ;;
      *) echo "ERROR: unknown argument: $1" >&2; exit 1 ;;
    esac
  done

  echo "Haven Backup portal installer"
  echo "============================="

  command -v git >/dev/null 2>&1 || { echo "ERROR: git is not installed (e.g. sudo apt-get install git)." >&2; exit 1; }
  command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker is not installed: https://docs.docker.com/engine/install/" >&2; exit 1; }
  docker compose version >/dev/null 2>&1 || { echo "ERROR: the Docker Compose v2 plugin is not available." >&2; exit 1; }
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: this user can't talk to Docker. Either add it to the docker group" >&2
    echo "  (sudo usermod -aG docker \"$USER\", then log out and back in) or run this as a user that can." >&2
    exit 1
  fi
  echo "[ok] git, Docker and Docker Compose found"
  if [ "$(id -u)" = 0 ]; then
    echo "[warn] Running as root -- the checkout will be root-owned. A regular user in the docker group is preferred."
  fi

  if [ -e "$dir" ]; then
    if [ -f "$dir/scripts/update.sh" ] && git -C "$dir" remote get-url origin 2>/dev/null | grep -q haven-backup; then
      echo "[info] Haven Backup is already installed at $dir."
      echo "       To update it:           $dir/scripts/update.sh"
      echo "       To re-run configuration: $dir/scripts/setup.sh"
      exit 0
    fi
    echo "ERROR: $dir already exists and isn't a Haven Backup checkout. Pick another location with --dir." >&2
    exit 1
  fi

  echo "Cloning $repo_url into $dir"
  git clone --quiet "$repo_url" "$dir"
  if [ -n "$version" ]; then
    if ! git -C "$dir" rev-parse "refs/tags/$version" >/dev/null 2>&1; then
      echo "ERROR: tag '$version' not found. Available:" >&2
      git -C "$dir" tag --list 'v*' --sort=-v:refname | head -n 10 >&2
      rm -rf "$dir"
      exit 1
    fi
    git -C "$dir" -c advice.detachedHead=false checkout --quiet "refs/tags/$version"
    echo "[ok] Checked out $version (scripts/update.sh <tag> moves between versions later)"
  else
    echo "[ok] Checked out $(git -C "$dir" describe --tags --always 2>/dev/null)"
  fi

  # setup.sh prompts for each setting; under `curl | bash` stdin is this script, so point
  # it at the terminal instead.
  # -r /dev/tty is true even with no controlling terminal; only opening it proves one exists.
  if (exec </dev/tty) 2>/dev/null; then
    echo
    "$dir/scripts/setup.sh" </dev/tty
  else
    echo
    echo "No terminal available for the interactive setup. Finish with:"
    echo "  $dir/scripts/setup.sh"
  fi
}

main "$@"

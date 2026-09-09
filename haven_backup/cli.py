"""Haven Backup command-line interface.

Every subcommand is non-interactive except `menu` and `browse`, so `backup`,
`prune`, and `healthcheck` are safe to run from cron or a systemd timer.
"""

import argparse
import json
import sys

from haven_backup.backends import build_backend
from haven_backup.backup_engine import BackupEngine
from haven_backup.config_manager import ConfigManager
from haven_backup.crypto_engine import build_crypto_engine
from haven_backup.health_engine import HealthEngine
from haven_backup.index_engine import IndexEngine
from haven_backup.logging_engine import LoggingEngine
from haven_backup.prune_engine import PruneEngine
from haven_backup.restore_engine import RestoreEngine
from haven_backup.storage_engine import StorageEngine
from haven_backup.update_engine import UpdateEngine


class Context:
    def __init__(self):
        self.config = ConfigManager()
        self.logger = LoggingEngine()
        self.backend = build_backend(self.config.get_destination())
        self.crypto_engine = build_crypto_engine()
        self.storage_engine = StorageEngine(self.backend, self.crypto_engine)
        self.index_engine = IndexEngine(self.backend)
        self.backup_engine = BackupEngine(
            self.backend, self.storage_engine, self.index_engine,
            self.config.get_backup_paths(), self.config.get_exclude_patterns(), self.logger,
        )
        self.restore_engine = RestoreEngine(self.backend, self.storage_engine, self.logger)
        self.health_engine = HealthEngine(self.backend, self.index_engine)
        self.prune_engine = PruneEngine(self.backend, self.index_engine, self.logger)

    def close(self):
        self.backend.close()


def cmd_init(args):
    from haven_backup.config_manager import DEFAULT_CONFIG_FILE
    from haven_backup.crypto_engine import DEFAULT_KEY_FILE, load_or_create_key

    config = ConfigManager()
    load_or_create_key()  # generates the key on first run, or confirms it's readable
    print(f"[init] Config:      {DEFAULT_CONFIG_FILE}")
    print(f"[init] Master key:  {DEFAULT_KEY_FILE} (back this up separately -- see docs/DISASTER_RECOVERY.md)")
    print(f"[init] Destination: {config.get_destination()}")
    print("[init] Edit backup_paths with: haven-backup config set-backup-paths <path> [<path> ...]")
    return 0


def cmd_backup(args):
    ctx = Context()
    if not ctx.config.get_backup_paths():
        print("[backup] No backup_paths configured. Run: haven-backup config set-backup-paths <path>...", file=sys.stderr)
        return 1
    try:
        snapshot_id = ctx.backup_engine.run_backup(snapshot_type=args.type)
        print(f"[backup] Snapshot completed: {snapshot_id}")
        return 0
    finally:
        ctx.close()


def cmd_snapshots(args):
    ctx = Context()
    try:
        for snapshot_id in ctx.restore_engine.list_snapshots():
            print(snapshot_id)
        return 0
    finally:
        ctx.close()


def cmd_restore(args):
    ctx = Context()
    try:
        if args.target == "full":
            restored = ctx.restore_engine.restore_full(args.snapshot_id, args.to, args.dry_run)
        else:
            restored = ctx.restore_engine.restore_paths(args.snapshot_id, args.paths, args.to, args.dry_run)

        prefix = "[restore:dry-run]" if args.dry_run else "[restore]"
        for path in restored:
            print(f"{prefix} {path}")
        print(f"{prefix} {len(restored)} file(s)")
        return 0
    except FileNotFoundError as e:
        print(f"[restore] {e}", file=sys.stderr)
        return 1
    finally:
        ctx.close()


def cmd_browse(args):
    from haven_backup.browser_engine import BrowserEngine

    ctx = Context()
    try:
        BrowserEngine(ctx.restore_engine).browse_snapshot(args.snapshot_id)
        return 0
    finally:
        ctx.close()


def cmd_healthcheck(args):
    ctx = Context()
    try:
        results = ctx.health_engine.run_health_check()
        print(json.dumps(results, indent=2))
        integrity = results["integrity"]
        healthy = not integrity["missing_chunks"] and not (
            results["disk_space"] and results["disk_space"]["low_space"]
        )
        return 0 if healthy else 1
    finally:
        ctx.close()


def cmd_prune(args):
    ctx = Context()
    try:
        result = ctx.prune_engine.prune(ctx.config.get_retention_policy(), dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0
    finally:
        ctx.close()


def cmd_update(args):
    config = ConfigManager()
    engine = UpdateEngine(config)
    updated = engine.run_update()
    if updated and not args.no_restart:
        engine.restart()
    return 0 if updated else 1


def cmd_config_show(args):
    print(json.dumps(ConfigManager().as_dict(), indent=2))
    return 0


def cmd_config_set_backup_paths(args):
    ConfigManager().set_backup_paths(args.paths)
    print(f"[config] backup_paths = {args.paths}")
    return 0


def cmd_config_set_exclude(args):
    ConfigManager().set_exclude_patterns(args.patterns)
    print(f"[config] exclude_patterns = {args.patterns}")
    return 0


def cmd_config_set_retention(args):
    ConfigManager().set_retention_policy(args.full, args.incremental)
    print(f"[config] retention_policy = {{'full': {args.full}, 'incremental': {args.incremental}}}")
    return 0


def cmd_config_set_destination_local(args):
    ConfigManager().set_destination_local(args.path)
    print(f"[config] destination = local:{args.path}")
    return 0


def cmd_config_set_destination_sftp(args):
    ConfigManager().set_destination_sftp(
        host=args.host, username=args.username, remote_path=args.remote_path,
        port=args.port, key_path=args.key_path, password=args.password,
        auto_add_host_key=args.auto_add_host_key,
    )
    print(f"[config] destination = sftp:{args.username}@{args.host}:{args.port}{args.remote_path}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="haven-backup", description="Encrypted, deduplicated backups.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Bootstrap config + encryption key").set_defaults(func=cmd_init)

    p = sub.add_parser("backup", help="Run a backup")
    p.add_argument("--type", choices=["full", "incremental"], default="full")
    p.set_defaults(func=cmd_backup)

    sub.add_parser("snapshots", help="List snapshots").set_defaults(func=cmd_snapshots)

    p = sub.add_parser("restore", help="Restore a full snapshot or specific paths")
    p.add_argument("snapshot_id")
    p.add_argument("target", nargs="?", default="full", choices=["full", "paths"])
    p.add_argument("paths", nargs="*", help="Paths to restore (only with target=paths)")
    p.add_argument("--to", help="Restore under this root instead of original locations")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("browse", help="Interactively browse a snapshot")
    p.add_argument("snapshot_id")
    p.set_defaults(func=cmd_browse)

    sub.add_parser("healthcheck", help="Check repo integrity, disk space, incomplete backups").set_defaults(func=cmd_healthcheck)

    p = sub.add_parser("prune", help="Apply retention policy and garbage-collect orphaned chunks")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("update", help="Git-pull the Haven Backup installation itself")
    p.add_argument("--no-restart", action="store_true")
    p.set_defaults(func=cmd_update)

    config_parser = sub.add_parser("config", help="View/edit configuration")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)

    config_sub.add_parser("show").set_defaults(func=cmd_config_show)

    p = config_sub.add_parser("set-backup-paths")
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_config_set_backup_paths)

    p = config_sub.add_parser("set-exclude")
    p.add_argument("patterns", nargs="+")
    p.set_defaults(func=cmd_config_set_exclude)

    p = config_sub.add_parser("set-retention")
    p.add_argument("--full", type=int, required=True)
    p.add_argument("--incremental", type=int, required=True)
    p.set_defaults(func=cmd_config_set_retention)

    dest_sub = config_sub.add_parser("set-destination").add_subparsers(dest="destination_type", required=True)

    p = dest_sub.add_parser("local")
    p.add_argument("path")
    p.set_defaults(func=cmd_config_set_destination_local)

    p = dest_sub.add_parser("sftp")
    p.add_argument("--host", required=True)
    p.add_argument("--username", required=True)
    p.add_argument("--remote-path", required=True)
    p.add_argument("--port", type=int, default=22)
    p.add_argument("--key-path", default=None)
    p.add_argument("--password", default=None, help="Prefer --key-path; a password is a weaker, unattended-unfriendly fallback")
    p.add_argument("--auto-add-host-key", action="store_true", help="Trust the host key on first connect (see docs/SFTP_SETUP.md)")
    p.set_defaults(func=cmd_config_set_destination_sftp)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

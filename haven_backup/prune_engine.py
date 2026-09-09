"""Retention: drop old snapshots, then garbage-collect any chunk nothing references."""

import json

from haven_backup.backends.base import StorageBackend
from haven_backup.index_engine import IndexEngine
from haven_backup.logging_engine import LoggingEngine


class PruneEngine:
    def __init__(self, backend: StorageBackend, index_engine: IndexEngine, logger: LoggingEngine = None):
        self.backend = backend
        self.index_engine = index_engine
        self.logger = logger or LoggingEngine()

    def _list_snapshots(self):
        names = [n[:-5] for n in self.backend.list_dir("snapshots") if n.endswith(".json")]
        full = sorted((n for n in names if n.startswith("full_")), reverse=True)
        incremental = sorted((n for n in names if n.startswith("incremental_")), reverse=True)
        return full, incremental

    def plan(self, retention_policy: dict):
        """Snapshot ids that would be deleted, oldest-first-in / newest-kept ordering applied."""
        full, incremental = self._list_snapshots()
        keep_full = retention_policy.get("full", 3)
        keep_incremental = retention_policy.get("incremental", 7)
        return full[keep_full:] + incremental[keep_incremental:]

    def prune(self, retention_policy: dict, dry_run: bool = False) -> dict:
        to_delete = self.plan(retention_policy)

        if dry_run:
            return {"deleted_snapshots": to_delete, "deleted_chunks": [], "dry_run": True}

        for snapshot_id in to_delete:
            self.backend.remove(f"snapshots/{snapshot_id}.json")
            self.logger.info("backup", f"Pruned snapshot: {snapshot_id}")

        deleted_chunks = self._garbage_collect()
        return {"deleted_snapshots": to_delete, "deleted_chunks": deleted_chunks, "dry_run": False}

    def _garbage_collect(self):
        referenced = set()
        for name in self.backend.list_dir("snapshots"):
            if not name.endswith(".json"):
                continue
            snapshot = json.loads(self.backend.read(f"snapshots/{name}"))
            for meta in snapshot.get("files", {}).values():
                referenced.update(meta.get("chunks", []))

        orphaned = self.index_engine.all_chunk_hashes() - referenced
        for chunk_hash in orphaned:
            self.backend.remove(f"data/{chunk_hash}.enc")
        self.index_engine.remove_chunks(orphaned)

        if orphaned:
            self.logger.info("backup", f"Garbage-collected {len(orphaned)} orphaned chunk(s).")
        return sorted(orphaned)

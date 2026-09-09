"""Restores files/folders/full snapshots from a repo back onto the local filesystem."""

import json
import os

from haven_backup.backends.base import StorageBackend
from haven_backup.logging_engine import LoggingEngine
from haven_backup.storage_engine import StorageEngine


class RestoreEngine:
    def __init__(self, backend: StorageBackend, storage_engine: StorageEngine, logger: LoggingEngine = None):
        self.backend = backend
        self.storage_engine = storage_engine
        self.logger = logger or LoggingEngine()

    def list_snapshots(self):
        names = [n[:-5] for n in self.backend.list_dir("snapshots") if n.endswith(".json")]
        return sorted(names, reverse=True)

    def load_snapshot(self, snapshot_id: str) -> dict:
        path = f"snapshots/{snapshot_id}.json"
        if not self.backend.exists(path):
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
        return json.loads(self.backend.read(path))

    # -----------------------------
    # Writing restored files locally
    # -----------------------------
    def _write_file(self, output_path: str, chunk_hashes) -> None:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        temp_path = output_path + ".tmp"
        with open(temp_path, "wb") as f:
            for chunk_hash in chunk_hashes:
                f.write(self.storage_engine.retrieve_chunk(chunk_hash))
        os.replace(temp_path, output_path)

    def _resolve_output_path(self, original_path: str, restore_root: str = None) -> str:
        if not restore_root:
            return original_path
        relative = original_path.lstrip("/\\")
        drive, relative = os.path.splitdrive(relative)  # strip a leading "C:" if present
        return os.path.join(restore_root, relative.lstrip("/\\"))

    def restore_file(self, file_path: str, metadata: dict, restore_root: str = None) -> str:
        output_path = self._resolve_output_path(file_path, restore_root)
        self._write_file(output_path, metadata.get("chunks", []))
        self.logger.info("restore", f"Restored: {file_path} -> {output_path}")
        return output_path

    # -----------------------------
    # Bulk restores
    # -----------------------------
    def restore_full(self, snapshot_id: str, restore_root: str = None, dry_run: bool = False):
        snapshot = self.load_snapshot(snapshot_id)
        return self._restore_matching(snapshot, lambda _: True, restore_root, dry_run)

    def restore_paths(self, snapshot_id: str, targets, restore_root: str = None, dry_run: bool = False):
        """Restore any file whose path starts with one of `targets` (files or folders)."""
        snapshot = self.load_snapshot(snapshot_id)
        return self._restore_matching(
            snapshot, lambda path: any(path.startswith(t) for t in targets), restore_root, dry_run
        )

    def _restore_matching(self, snapshot, predicate, restore_root, dry_run):
        restored = []
        for file_path, meta in snapshot.get("files", {}).items():
            if not predicate(file_path):
                continue
            if dry_run:
                restored.append(file_path)
                continue
            self.restore_file(file_path, meta, restore_root)
            restored.append(file_path)
        return restored

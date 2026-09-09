"""Scans configured paths, chunks + dedups + encrypts them, and commits a snapshot."""

import fnmatch
import json
import os
import time
from datetime import datetime, timezone

from haven_backup.backends.base import StorageBackend
from haven_backup.index_engine import IndexEngine
from haven_backup.logging_engine import LoggingEngine
from haven_backup.storage_engine import StorageEngine


class BackupEngine:
    def __init__(
        self,
        backend: StorageBackend,
        storage_engine: StorageEngine,
        index_engine: IndexEngine,
        backup_paths,
        exclude_patterns=None,
        logger: LoggingEngine = None,
    ):
        self.backend = backend
        self.storage_engine = storage_engine
        self.index_engine = index_engine
        self.backup_paths = backup_paths
        self.exclude_patterns = exclude_patterns or []
        self.logger = logger or LoggingEngine()

    # -----------------------------
    # Scan
    # -----------------------------
    def _is_excluded(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in self.exclude_patterns)

    def scan_files(self):
        files = []
        for base_path in self.backup_paths:
            base_path = os.path.expanduser(base_path)

            if os.path.isfile(base_path):
                if not self._is_excluded(base_path):
                    files.append(base_path)
                continue

            for root, dirnames, filenames in os.walk(base_path):
                dirnames[:] = [d for d in dirnames if not self._is_excluded(os.path.join(root, d))]
                for name in filenames:
                    full_path = os.path.join(root, name)
                    if not self._is_excluded(full_path):
                        files.append(full_path)
        return files

    # -----------------------------
    # Per-file backup
    # -----------------------------
    def backup_file(self, file_path: str):
        chunk_hashes = []
        try:
            for chunk in self.storage_engine.chunk_file(file_path):
                chunk_hash = self.storage_engine.store_chunk(chunk)
                self.index_engine.add_chunk(chunk_hash, len(chunk))
                chunk_hashes.append(chunk_hash)
            return chunk_hashes
        except (OSError, PermissionError) as e:
            self.logger.error("backup", f"Failed to back up {file_path}: {e}")
            raise

    # -----------------------------
    # Staging (resume support)
    # -----------------------------
    def _staging_path(self, snapshot_id):
        return f"staging/{snapshot_id}.json"

    def _save_staging(self, snapshot_id, data):
        self.backend.write(self._staging_path(snapshot_id), json.dumps(data, indent=2).encode("utf-8"))

    def _load_staging(self, snapshot_id):
        path = self._staging_path(snapshot_id)
        if self.backend.exists(path):
            return json.loads(self.backend.read(path))
        return None

    def _find_resumable_snapshot(self, snapshot_type):
        for snapshot_id in self.index_engine.list_incomplete_snapshots():
            if snapshot_id.startswith(f"{snapshot_type}_"):
                return snapshot_id
        return None

    # -----------------------------
    # Run backup
    # -----------------------------
    def run_backup(self, snapshot_type: str = "full") -> str:
        if snapshot_type not in ("full", "incremental"):
            snapshot_type = "full"

        # Resume a prior interrupted run of the same type if one is staged, rather than
        # minting a fresh timestamped id that would never match old staging data anyway.
        snapshot_id = self._find_resumable_snapshot(snapshot_type)
        if snapshot_id:
            staging_data = self._load_staging(snapshot_id)
            self.logger.warning("backup", f"Resuming incomplete backup: {snapshot_id}")
        else:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            snapshot_id = f"{snapshot_type}_{timestamp}"
            staging_data = {
                "snapshot_id": snapshot_id,
                "type": snapshot_type,
                "created": datetime.now(timezone.utc).isoformat(),
                "files": {},
            }

        self.logger.info("backup", f"Starting {snapshot_type} backup: {snapshot_id}")

        files = self.scan_files()
        self.logger.info("backup", f"{len(files)} files detected for backup")

        errors = 0
        for file_path in files:
            if file_path in staging_data["files"]:
                continue  # already processed in a prior, interrupted run

            try:
                chunk_hashes = self.backup_file(file_path)
                staging_data["files"][file_path] = {
                    "chunks": chunk_hashes,
                    "timestamp": time.time(),
                }
                self._save_staging(snapshot_id, staging_data)
            except (OSError, PermissionError):
                errors += 1  # already logged in backup_file; keep going with the rest

        self.backend.write(f"snapshots/{snapshot_id}.json", json.dumps(staging_data, indent=2).encode("utf-8"))
        self.index_engine.clear_staging_snapshot(snapshot_id)

        self.logger.info(
            "backup",
            f"Backup completed: {snapshot_id} ({len(staging_data['files'])} files backed up, {errors} errors)",
        )
        return snapshot_id

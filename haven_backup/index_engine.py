"""Tracks known chunks and in-progress (staged) snapshots, all via the backend."""

import json
from datetime import datetime, timezone

from haven_backup.backends.base import StorageBackend

INDEX_PATH = "metadata/index.json"


class IndexEngine:
    def __init__(self, backend: StorageBackend):
        self.backend = backend
        self.index = self._load()

    def _load(self):
        if self.backend.exists(INDEX_PATH):
            return json.loads(self.backend.read(INDEX_PATH))
        return {"chunks": {}}

    def _save(self):
        self.backend.write(INDEX_PATH, json.dumps(self.index, indent=2).encode("utf-8"))

    def add_chunk(self, chunk_hash: str, size: int):
        if chunk_hash not in self.index["chunks"]:
            self.index["chunks"][chunk_hash] = {"size": size, "created": datetime.now(timezone.utc).isoformat()}
            self._save()

    def chunk_exists(self, chunk_hash: str) -> bool:
        return chunk_hash in self.index["chunks"]

    def all_chunk_hashes(self):
        return set(self.index["chunks"].keys())

    def remove_chunks(self, chunk_hashes):
        changed = False
        for chunk_hash in chunk_hashes:
            if chunk_hash in self.index["chunks"]:
                del self.index["chunks"][chunk_hash]
                changed = True
        if changed:
            self._save()

    # -----------------------------
    # Staging (resumable backups)
    # -----------------------------
    def list_incomplete_snapshots(self):
        return [name[:-5] for name in self.backend.list_dir("staging") if name.endswith(".json")]

    def clear_staging_snapshot(self, snapshot_id: str):
        self.backend.remove(f"staging/{snapshot_id}.json")

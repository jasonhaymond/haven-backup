"""Repository integrity, disk space, and staging/backlog checks."""

import json

from haven_backup.backends.base import StorageBackend
from haven_backup.index_engine import IndexEngine


class HealthEngine:
    def __init__(self, backend: StorageBackend, index_engine: IndexEngine):
        self.backend = backend
        self.index_engine = index_engine

    def check_repo_integrity(self):
        results = {"snapshots_checked": 0, "missing_chunks": []}
        for name in self.backend.list_dir("snapshots"):
            if not name.endswith(".json"):
                continue
            results["snapshots_checked"] += 1
            snapshot = json.loads(self.backend.read(f"snapshots/{name}"))
            for meta in snapshot.get("files", {}).values():
                for chunk_hash in meta.get("chunks", []):
                    if not self.backend.exists(f"data/{chunk_hash}.enc"):
                        results["missing_chunks"].append(chunk_hash)
        return results

    def check_disk_space(self):
        usage = self.backend.disk_usage()
        if usage is None:
            return None
        total, used, free = usage
        return {
            "total_gb": total // (2**30),
            "used_gb": used // (2**30),
            "free_gb": free // (2**30),
            "low_space": free < 0.1 * total,
        }

    def check_incomplete_backups(self):
        return self.index_engine.list_incomplete_snapshots()

    def run_health_check(self) -> dict:
        return {
            "integrity": self.check_repo_integrity(),
            "disk_space": self.check_disk_space(),
            "incomplete_backups": self.check_incomplete_backups(),
        }

import json

from haven_backup.index_engine import IndexEngine
from haven_backup.prune_engine import PruneEngine


def _write_snapshot(backend, snapshot_id, chunk_hashes):
    backend.write(f"snapshots/{snapshot_id}.json", json.dumps({
        "snapshot_id": snapshot_id,
        "files": {"f.txt": {"chunks": chunk_hashes}},
    }).encode("utf-8"))


def test_prune_keeps_only_retained_snapshots(backend):
    for i in range(5):
        _write_snapshot(backend, f"full_{i}", [f"hash{i}"])

    index = IndexEngine(backend)
    for i in range(5):
        index.add_chunk(f"hash{i}", 10)
        backend.write(f"data/hash{i}.enc", b"x")

    prune = PruneEngine(backend, index)
    result = prune.prune({"full": 2, "incremental": 7}, dry_run=False)

    remaining = sorted(n[:-5] for n in backend.list_dir("snapshots"))
    assert remaining == ["full_3", "full_4"]  # newest 2 of 5, by lexicographic/time order
    assert set(result["deleted_snapshots"]) == {"full_0", "full_1", "full_2"}


def test_prune_garbage_collects_orphaned_chunks(backend):
    _write_snapshot(backend, "full_1", ["kept_hash"])
    index = IndexEngine(backend)
    index.add_chunk("kept_hash", 10)
    index.add_chunk("orphan_hash", 10)
    backend.write("data/kept_hash.enc", b"x")
    backend.write("data/orphan_hash.enc", b"y")

    prune = PruneEngine(backend, index)
    result = prune.prune({"full": 5, "incremental": 5}, dry_run=False)

    assert result["deleted_chunks"] == ["orphan_hash"]
    assert backend.exists("data/kept_hash.enc")
    assert not backend.exists("data/orphan_hash.enc")


def test_dry_run_prune_deletes_nothing(backend):
    for i in range(3):
        _write_snapshot(backend, f"full_{i}", [])
    index = IndexEngine(backend)

    prune = PruneEngine(backend, index)
    result = prune.prune({"full": 1, "incremental": 1}, dry_run=True)

    assert result["dry_run"] is True
    assert len(backend.list_dir("snapshots")) == 3

import os

from haven_backup.backup_engine import BackupEngine
from haven_backup.index_engine import IndexEngine
from haven_backup.restore_engine import RestoreEngine
from haven_backup.storage_engine import StorageEngine


def _make_source_tree(tmp_path):
    source = tmp_path / "source"
    (source / "sub").mkdir(parents=True)
    (source / "a.txt").write_text("file a contents")
    (source / "sub" / "b.txt").write_text("file b contents")
    (source / "ignored.log").write_text("should be excluded")
    return source


def test_full_backup_then_restore_roundtrip(tmp_path, backend, crypto_engine):
    source = _make_source_tree(tmp_path)
    storage = StorageEngine(backend, crypto_engine)
    index = IndexEngine(backend)
    backup = BackupEngine(backend, storage, index, [str(source)], exclude_patterns=["*.log"])

    snapshot_id = backup.run_backup(snapshot_type="full")

    restore_root = tmp_path / "restored"
    restore = RestoreEngine(backend, storage)
    restored = restore.restore_full(snapshot_id, restore_root=str(restore_root))

    assert len(restored) == 2  # a.txt + sub/b.txt, ignored.log excluded
    assert not any(p.endswith("ignored.log") for p in restored)

    restored_a = next(p for p in restored if p.endswith("a.txt"))
    output_path = restore._resolve_output_path(restored_a, str(restore_root))
    assert open(output_path).read() == "file a contents"


def test_dry_run_restore_does_not_write_files(tmp_path, backend, crypto_engine):
    source = _make_source_tree(tmp_path)
    storage = StorageEngine(backend, crypto_engine)
    index = IndexEngine(backend)
    backup = BackupEngine(backend, storage, index, [str(source)], exclude_patterns=["*.log"])
    snapshot_id = backup.run_backup(snapshot_type="full")

    restore_root = tmp_path / "restored_dry"
    restore = RestoreEngine(backend, storage)
    restore.restore_full(snapshot_id, restore_root=str(restore_root), dry_run=True)

    assert not restore_root.exists()


def test_incomplete_backup_resumes_on_rerun(tmp_path, backend, crypto_engine):
    source = _make_source_tree(tmp_path)
    storage = StorageEngine(backend, crypto_engine)
    index = IndexEngine(backend)
    backup = BackupEngine(backend, storage, index, [str(source)], exclude_patterns=["*.log"])

    # Simulate a prior run that got through a.txt and was then killed before b.txt.
    stale_snapshot_id = "full_20260101000000"
    backup._save_staging(stale_snapshot_id, {
        "snapshot_id": stale_snapshot_id, "type": "full", "created": "x",
        "files": {str(source / "a.txt"): {"chunks": ["deadbeef"], "timestamp": 0}},
    })
    assert stale_snapshot_id in index.list_incomplete_snapshots()

    result_id = backup.run_backup(snapshot_type="full")

    # The rerun must pick up the stale staging id, not mint a brand-new one.
    assert result_id == stale_snapshot_id
    assert stale_snapshot_id not in index.list_incomplete_snapshots()

    snapshot = restore_engine_snapshot(backend, stale_snapshot_id)
    assert str(source / "a.txt") in snapshot["files"]
    assert str(source / "sub" / "b.txt") in snapshot["files"]
    # a.txt's chunk from the "prior run" was never re-processed (kept the stale hash).
    assert snapshot["files"][str(source / "a.txt")]["chunks"] == ["deadbeef"]


def restore_engine_snapshot(backend, snapshot_id):
    import json
    return json.loads(backend.read(f"snapshots/{snapshot_id}.json"))

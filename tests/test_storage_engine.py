from haven_backup.storage_engine import StorageEngine


def test_store_and_retrieve_chunk(backend, crypto_engine):
    storage = StorageEngine(backend, crypto_engine)
    chunk_hash = storage.store_chunk(b"hello world")
    assert storage.retrieve_chunk(chunk_hash) == b"hello world"


def test_dedup_does_not_rewrite_existing_chunk(backend, crypto_engine):
    storage = StorageEngine(backend, crypto_engine)
    hash1 = storage.store_chunk(b"same content")
    written_once = backend.read(f"data/{hash1}.enc")

    hash2 = storage.store_chunk(b"same content")
    written_twice = backend.read(f"data/{hash2}.enc")

    assert hash1 == hash2
    assert written_once == written_twice  # unchanged -- not re-encrypted/rewritten


def test_retrieve_missing_chunk_raises(backend, crypto_engine):
    storage = StorageEngine(backend, crypto_engine)
    try:
        storage.retrieve_chunk("0" * 64)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_chunk_file_splits_by_size(tmp_path, backend, crypto_engine):
    file_path = tmp_path / "data.bin"
    file_path.write_bytes(b"x" * 2500)

    storage = StorageEngine(backend, crypto_engine)
    chunks = list(storage.chunk_file(str(file_path), chunk_size=1000))

    assert [len(c) for c in chunks] == [1000, 1000, 500]

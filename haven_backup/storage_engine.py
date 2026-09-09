"""Content-addressable, deduplicated, encrypted chunk storage on top of a backend."""

import hashlib

from haven_backup.backends.base import StorageBackend
from haven_backup.crypto_engine import CryptoEngine

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB


class StorageEngine:
    def __init__(self, backend: StorageBackend, crypto_engine: CryptoEngine):
        self.backend = backend
        self.crypto_engine = crypto_engine

    def chunk_file(self, file_path: str, chunk_size: int = DEFAULT_CHUNK_SIZE):
        """Generator yielding a local file's contents in fixed-size chunks."""
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    @staticmethod
    def hash_chunk(chunk: bytes) -> str:
        return hashlib.sha256(chunk).hexdigest()

    def store_chunk(self, chunk: bytes) -> str:
        """Encrypt + store a chunk if not already present. Returns its content hash."""
        chunk_hash = self.hash_chunk(chunk)
        relpath = f"data/{chunk_hash}.enc"

        if self.backend.exists(relpath):
            return chunk_hash  # already stored under a previous snapshot -- dedup hit

        encrypted = self.crypto_engine.encrypt_chunk(chunk)
        self.backend.write(relpath, encrypted)
        return chunk_hash

    def retrieve_chunk(self, chunk_hash: str) -> bytes:
        relpath = f"data/{chunk_hash}.enc"
        if not self.backend.exists(relpath):
            raise FileNotFoundError(f"Chunk not found in repository: {chunk_hash}")
        encrypted = self.backend.read(relpath)
        return self.crypto_engine.decrypt_chunk(encrypted)

    def chunk_size_on_disk(self, chunk_hash: str) -> int:
        return len(self.backend.read(f"data/{chunk_hash}.enc"))

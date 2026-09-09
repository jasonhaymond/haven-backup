import pytest

from haven_backup.backends.local_backend import LocalBackend
from haven_backup.crypto_engine import CryptoEngine


@pytest.fixture
def backend(tmp_path):
    return LocalBackend(str(tmp_path / "repo"))


@pytest.fixture
def crypto_engine():
    return CryptoEngine(key=b"0" * 32)

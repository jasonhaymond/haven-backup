"""AES-256-GCM chunk encryption with a persisted (or passphrase-derived) master key."""

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DEFAULT_KEY_FILE = os.path.expanduser("~/.haven_backup/master.key")
PASSPHRASE_ENV_VAR = "HAVEN_BACKUP_PASSPHRASE"
PBKDF2_ITERATIONS = 600_000


class CryptoEngine:
    """Encrypts/decrypts chunks with a fixed 256-bit key using AES-GCM."""

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("Master key must be 32 bytes (256 bits)")
        self.master_key = key
        self._aesgcm = AESGCM(key)

    def encrypt_chunk(self, plaintext: bytes, associated_data: bytes = None) -> bytes:
        nonce = os.urandom(12)  # 96-bit nonce, unique per encryption under this key
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext

    def decrypt_chunk(self, encrypted_data: bytes, associated_data: bytes = None) -> bytes:
        nonce, ciphertext = encrypted_data[:12], encrypted_data[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, associated_data)


def _derive_key_from_passphrase(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return kdf.derive(passphrase.encode("utf-8"))


def _lock_down(path: str) -> None:
    try:
        os.chmod(path, 0o600)
    except (AttributeError, NotImplementedError, OSError):
        pass  # best-effort; not meaningful on some filesystems (e.g. exFAT, some Windows setups)


def load_or_create_key(key_file: str = DEFAULT_KEY_FILE) -> bytes:
    """
    Resolve the master key for this machine.

    If HAVEN_BACKUP_PASSPHRASE is set, the key is deterministically derived from it
    (via PBKDF2) using a non-secret salt stored next to the key file. This lets you
    recover the key on a fresh machine by re-entering the passphrase, with nothing
    to physically lose. Otherwise a random key is generated once and persisted to
    key_file -- in that mode, key_file IS the backup encryption secret and losing it
    means the backups are permanently unrecoverable. See docs/DISASTER_RECOVERY.md.
    """
    passphrase = os.environ.get(PASSPHRASE_ENV_VAR)

    if passphrase:
        salt_file = key_file + ".salt"
        if os.path.exists(salt_file):
            with open(salt_file, "rb") as f:
                salt = f.read()
        else:
            salt = os.urandom(16)
            os.makedirs(os.path.dirname(salt_file), exist_ok=True)
            with open(salt_file, "wb") as f:
                f.write(salt)
            _lock_down(salt_file)
        return _derive_key_from_passphrase(passphrase, salt)

    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read()

    key = AESGCM.generate_key(bit_length=256)
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    with open(key_file, "wb") as f:
        f.write(key)
    _lock_down(key_file)
    return key


def build_crypto_engine(key_file: str = DEFAULT_KEY_FILE) -> CryptoEngine:
    return CryptoEngine(load_or_create_key(key_file))

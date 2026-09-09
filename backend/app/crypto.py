"""Encrypts secrets (SSH private keys, borg passphrases) at rest in the DB.

This protects the SQLite file at rest (e.g. a stolen disk/backup of the
portal's own data dir); it does not protect against someone who already has
access to a live, unlocked instance of the portal process itself.
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import config


def _load_or_create_key() -> bytes:
    if config.SECRET_KEY_FILE.exists():
        return config.SECRET_KEY_FILE.read_bytes()

    key = AESGCM.generate_key(bit_length=256)
    config.SECRET_KEY_FILE.write_bytes(key)
    try:
        os.chmod(config.SECRET_KEY_FILE, 0o600)
    except (AttributeError, NotImplementedError, OSError):
        pass
    return key


_aesgcm = None


def _engine() -> AESGCM:
    global _aesgcm
    if _aesgcm is None:
        _aesgcm = AESGCM(_load_or_create_key())
    return _aesgcm


def encrypt(plaintext: str) -> bytes:
    nonce = os.urandom(12)
    ciphertext = _engine().encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt(blob: bytes) -> str:
    nonce, ciphertext = blob[:12], blob[12:]
    return _engine().decrypt(nonce, ciphertext, None).decode("utf-8")

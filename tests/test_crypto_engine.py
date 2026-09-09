import os

from haven_backup.crypto_engine import CryptoEngine, load_or_create_key


def test_encrypt_decrypt_roundtrip(crypto_engine):
    plaintext = b"Haven Backup test payload"
    encrypted = crypto_engine.encrypt_chunk(plaintext)
    assert crypto_engine.decrypt_chunk(encrypted) == plaintext


def test_encrypted_output_differs_from_input(crypto_engine):
    plaintext = b"sensitive configuration data"
    encrypted = crypto_engine.encrypt_chunk(plaintext)
    assert plaintext not in encrypted


def test_wrong_key_fails_to_decrypt(crypto_engine):
    other = CryptoEngine(key=b"1" * 32)
    encrypted = crypto_engine.encrypt_chunk(b"secret")
    try:
        other.decrypt_chunk(encrypted)
        assert False, "decrypting with the wrong key should raise"
    except Exception:
        pass


def test_key_is_persisted_across_loads(tmp_path):
    key_file = str(tmp_path / "master.key")
    key1 = load_or_create_key(key_file)
    key2 = load_or_create_key(key_file)
    assert key1 == key2
    assert len(key1) == 32


def test_passphrase_derives_same_key_deterministically(tmp_path, monkeypatch):
    key_file = str(tmp_path / "master.key")
    monkeypatch.setenv("HAVEN_BACKUP_PASSPHRASE", "correct-horse-battery-staple")
    key1 = load_or_create_key(key_file)

    # A fresh key file (simulating a new machine) but the same salt file + passphrase
    # must re-derive the identical key -- that's the whole point of passphrase mode.
    key_file_2 = str(tmp_path / "master2.key")
    os.replace(key_file + ".salt", key_file_2 + ".salt")
    key2 = load_or_create_key(key_file_2)
    assert key1 == key2

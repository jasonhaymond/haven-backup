from app import crypto, security


def test_crypto_roundtrip():
    blob = crypto.encrypt("super secret ssh key contents")
    assert crypto.decrypt(blob) == "super secret ssh key contents"


def test_crypto_output_does_not_contain_plaintext():
    plaintext = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    blob = crypto.encrypt(plaintext)
    assert b"BEGIN OPENSSH" not in blob


def test_password_hash_and_verify():
    hashed = security.hash_password("correct horse battery staple")
    assert security.verify_password("correct horse battery staple", hashed) is True
    assert security.verify_password("wrong password", hashed) is False


def test_session_token_roundtrip():
    token = security.create_session_token(user_id=42)
    assert security.read_session_token(token) == 42


def test_tampered_session_token_rejected():
    token = security.create_session_token(user_id=42)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert security.read_session_token(tampered) is None


def test_garbage_session_token_rejected():
    assert security.read_session_token("not-a-real-token") is None

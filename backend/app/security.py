"""Password hashing and signed session cookies (no JWT library needed)."""

import os

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import config


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _load_or_create_session_secret() -> str:
    if config.SESSION_SECRET_FILE.exists():
        return config.SESSION_SECRET_FILE.read_text().strip()

    secret = os.urandom(32).hex()
    config.SESSION_SECRET_FILE.write_text(secret)
    try:
        os.chmod(config.SESSION_SECRET_FILE, 0o600)
    except (AttributeError, NotImplementedError, OSError):
        pass
    return secret


_serializer = None


def _get_serializer() -> URLSafeTimedSerializer:
    global _serializer
    if _serializer is None:
        _serializer = URLSafeTimedSerializer(_load_or_create_session_secret(), salt="haven-backup-session")
    return _serializer


def create_session_token(user_id: int) -> str:
    return _get_serializer().dumps({"user_id": user_id})


def read_session_token(token: str) -> int | None:
    """Returns the user_id encoded in a valid, unexpired token, or None."""
    try:
        data = _get_serializer().loads(token, max_age=config.SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")

"""Tests scripts/reset_password.py's actual logic by importing and calling it
directly, rather than via subprocess -- getpass.getpass() ignores piped stdin
on Windows (bypasses redirection entirely, reading the real console instead),
which would make a subprocess-based interactive test unreliable/hang there.
Calling main() in-process and monkeypatching getpass.getpass sidesteps that
entirely and works identically on every platform.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlmodel import select

from app import security
from app.models import User

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "reset_password.py"


@pytest.fixture
def reset_password_module(db_session, monkeypatch):
    # The script imports `from app.db import engine` at module scope, bound to the
    # real production engine -- point it at this test's isolated engine instead.
    import app.db as db_module

    monkeypatch.setattr(db_module, "engine", db_session.get_bind())

    spec = importlib.util.spec_from_file_location("reset_password_script", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["reset_password_script"] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "engine", db_session.get_bind())
    yield module
    del sys.modules["reset_password_script"]


def _make_user(db_session, username="jason", password="original-password"):
    user = User(username=username, password_hash=security.hash_password(password))
    db_session.add(user)
    db_session.commit()
    return user


def test_generate_mode_sets_a_working_random_password(reset_password_module, db_session, monkeypatch, capsys):
    _make_user(db_session, "jason")
    monkeypatch.setattr(sys, "argv", ["reset_password.py", "jason", "--generate"])

    exit_code = reset_password_module.main()

    assert exit_code == 0
    printed = capsys.readouterr().out
    assert "New password:" in printed

    new_password = printed.split("New password:")[1].splitlines()[0].strip()
    db_session.expire_all()
    user = db_session.exec(select(User).where(User.username == "jason")).first()
    assert security.verify_password(new_password, user.password_hash) is True
    assert security.verify_password("original-password", user.password_hash) is False


def test_interactive_mode_prompts_and_sets_password(reset_password_module, db_session, monkeypatch):
    _make_user(db_session, "jason")
    monkeypatch.setattr(sys, "argv", ["reset_password.py", "jason"])

    responses = iter(["new-correct-password", "new-correct-password"])
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: next(responses))

    exit_code = reset_password_module.main()

    assert exit_code == 0
    db_session.expire_all()
    user = db_session.exec(select(User).where(User.username == "jason")).first()
    assert security.verify_password("new-correct-password", user.password_hash) is True


def test_mismatched_passwords_rejected(reset_password_module, db_session, monkeypatch):
    _make_user(db_session, "jason")
    monkeypatch.setattr(sys, "argv", ["reset_password.py", "jason"])

    responses = iter(["one-password", "a-different-password"])
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: next(responses))

    assert reset_password_module.main() == 1


def test_unknown_user_rejected_cleanly(reset_password_module, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["reset_password.py", "no-such-user", "--generate"])
    assert reset_password_module.main() == 1


def test_generated_password_too_short_rejected(reset_password_module, db_session, monkeypatch):
    _make_user(db_session, "jason")
    monkeypatch.setattr(sys, "argv", ["reset_password.py", "jason"])
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: "short")

    assert reset_password_module.main() == 1

from sqlmodel import Session, select

from app import __version__
from app.models import AppMeta
from app.version_stamp import stamp_current_version


def test_stamp_creates_row_on_first_call(db_session):
    meta = stamp_current_version(db_session)
    assert meta.version == __version__

    rows = db_session.exec(select(AppMeta)).all()
    assert len(rows) == 1


def test_stamp_updates_existing_row_rather_than_duplicating(db_session, monkeypatch):
    stamp_current_version(db_session)

    monkeypatch.setattr("app.version_stamp.__version__", "9.9.9")
    meta = stamp_current_version(db_session)

    assert meta.version == "9.9.9"
    rows = db_session.exec(select(AppMeta)).all()
    assert len(rows) == 1


def test_app_startup_stamps_version(client):
    """The FastAPI app's lifespan stamps AppMeta on startup -- exercised through the
    real app via the `client` fixture (which enters the TestClient context manager,
    running lifespan) rather than calling the helper directly."""
    from app.db import engine

    with Session(engine) as session:
        meta = session.exec(select(AppMeta)).first()
    assert meta is not None
    assert meta.version == __version__

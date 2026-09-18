"""Stamps the running app version into the database on every startup.

This is what makes a backup snapshot of the database self-identifying --
scripts/update.sh and docs/BACKUP.md read this value (not the git tree,
which can be ahead of what a not-yet-rebuilt container is actually running)
to label pre-update snapshots by the version that was live when they were taken.
"""

from datetime import datetime, timezone

from sqlmodel import Session, select

from app import __version__
from app.models import AppMeta


def stamp_current_version(session: Session) -> AppMeta:
    meta = session.exec(select(AppMeta)).first()
    if meta is None:
        meta = AppMeta(version=__version__)
    else:
        meta.version = __version__
        meta.updated_at = datetime.now(timezone.utc)
    session.add(meta)
    session.commit()
    session.refresh(meta)
    return meta

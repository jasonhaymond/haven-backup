#!/usr/bin/env python3
"""Prints the app version stamped in the database (app.models.AppMeta).

Used by scripts/update.sh and the manual backup commands in docs/BACKUP.md
to label a snapshot by the version that was actually running against that
database -- not the git tree's version, which can be ahead of what a
not-yet-rebuilt container is running.

    docker compose exec -T backend python scripts/db_version.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import AppMeta  # noqa: E402


def main():
    with Session(engine) as session:
        meta = session.exec(select(AppMeta)).first()
    print(meta.version if meta else "unknown")
    return 0


if __name__ == "__main__":
    sys.exit(main())

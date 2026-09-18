#!/usr/bin/env python3
"""Create an additional admin user.

There's no signup endpoint beyond the one-time `/api/auth/setup` (only usable
while the User table is empty) -- deliberately, so the portal can't grow new
logins from the outside. Run this on the host/container that has access to
the portal's database instead:

    python backend/scripts/create_user.py <username>
    # or, in Docker:
    docker compose exec backend python scripts/create_user.py <username>
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app import security  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import User  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <username>", file=sys.stderr)
        return 1

    username = sys.argv[1]
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1

    init_db()
    with Session(engine) as session:
        if session.exec(select(User).where(User.username == username)).first():
            print(f"User '{username}' already exists.", file=sys.stderr)
            return 1

        user = User(username=username, password_hash=security.hash_password(password))
        session.add(user)
        session.commit()

    print(f"Created user '{username}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Reset an existing user's password.

There's no self-service "forgot password" flow in the UI -- deliberately,
since that would mean the portal accepting some kind of unauthenticated
request as proof of identity, and it holds SSH keys/Borg passphrases (see
docs/SECURITY.md). This is the supported way to actually do it, run on the
host/container that has access to the portal's database:

    python backend/scripts/reset_password.py <username>
    python backend/scripts/reset_password.py <username> --generate
    # or, in Docker:
    docker compose exec backend python scripts/reset_password.py <username>

See also create_user.py, for adding an admin rather than resetting one.
"""

import getpass
import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app import security  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import User  # noqa: E402


def generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    generate = "--generate" in sys.argv[1:]

    if len(args) != 1:
        print(f"Usage: {sys.argv[0]} <username> [--generate]", file=sys.stderr)
        return 1
    username = args[0]

    if generate:
        password = generate_password()
    else:
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm new password: ")
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            return 1

    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1

    init_db()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            print(f"No such user: '{username}'. Use create_user.py to add one instead.", file=sys.stderr)
            return 1

        user.password_hash = security.hash_password(password)
        session.add(user)
        session.commit()

    print(f"Password reset for '{username}'.")
    if generate:
        print(f"New password: {password}")
        print("Save this now -- it cannot be shown or recovered again after this.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

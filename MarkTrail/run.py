from __future__ import annotations

import argparse
from getpass import getpass
import os

from app.db import Database, hash_password, utc_now
from app.server import run


def create_initial_admin(
    db: Database,
    username: str,
    full_name: str,
    password: str,
) -> int:
    username = username.strip()
    full_name = full_name.strip()
    if not username or not full_name:
        raise ValueError("Username and full name are required.")
    if len(password) < 12:
        raise ValueError("Administrator password must be at least 12 characters.")

    db.init(seed_demo=False)
    salt, password_hash = hash_password(password)
    with db.transaction() as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise ValueError("Initial admin can only be created before any users exist.")
        cursor = conn.execute(
            """
            INSERT INTO users
            (username, full_name, role, password_salt, password_hash, created_at)
            VALUES (?, ?, 'admin', ?, ?, ?)
            """,
            (username, full_name, salt, password_hash, utc_now()),
        )
        return int(cursor.lastrowid)


def main():
    parser = argparse.ArgumentParser(description="MarkTrail academic marks tracking system")
    parser.add_argument("--init", action="store_true", help="Initialize database and exit")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the demo database")
    parser.add_argument("--seed-demo", action="store_true", help="Explicitly seed synthetic demo data")
    parser.add_argument("--no-seed", action="store_true", help="Do not seed demo data")
    parser.add_argument(
        "--create-admin",
        action="store_true",
        help="Interactively create the first administrator in an empty database",
    )
    args = parser.parse_args()

    if args.create_admin:
        db = Database()
        username = input("Administrator username: ")
        full_name = input("Administrator full name: ")
        password = getpass("Administrator password (12+ characters): ")
        confirmation = getpass("Confirm administrator password: ")
        if password != confirmation:
            parser.error("Passwords do not match.")
        try:
            user_id = create_initial_admin(db, username, full_name, password)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"Initial administrator created (user ID {user_id}).")
        return

    if args.reset:
        db = Database()
        if db.path.exists():
            db.path.unlink()
        db.init(seed_demo=args.seed_demo and not args.no_seed)
        print(f"Database reset: {db.path}")
        return

    if args.init:
        db = Database()
        db.init(seed_demo=args.seed_demo and not args.no_seed)
        print(f"Database initialized: {db.path}")
        return

    if args.seed_demo:
        os.environ["MARKTRAIL_SEED_DEMO"] = "1"
    elif args.no_seed:
        os.environ["MARKTRAIL_SEED_DEMO"] = "0"

    run()


if __name__ == "__main__":
    main()

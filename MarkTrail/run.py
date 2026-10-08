from __future__ import annotations

import argparse
import os

from app.db import Database
from app.server import run


def main():
    parser = argparse.ArgumentParser(description="MarkTrail academic marks tracking system")
    parser.add_argument("--init", action="store_true", help="Initialize database and exit")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the demo database")
    parser.add_argument("--no-seed", action="store_true", help="Do not seed demo data")
    args = parser.parse_args()

    if args.reset:
        db = Database()
        if db.path.exists():
            db.path.unlink()
        db.init(seed_demo=not args.no_seed)
        print(f"Database reset: {db.path}")
        return

    if args.init:
        db = Database()
        db.init(seed_demo=not args.no_seed)
        print(f"Database initialized: {db.path}")
        return

    if args.no_seed:
        os.environ["MARKTRAIL_SEED_DEMO"] = "0"

    run()


if __name__ == "__main__":
    main()

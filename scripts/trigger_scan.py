"""Manually trigger a scan — demo safety net.

Usage:
    # Scan one user
    uv run python scripts/trigger_scan.py --user-id <telegram_user_id>

    # Scan all users
    uv run python scripts/trigger_scan.py --all
"""

import argparse
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from src.db.schema import init_db
from src.pipeline.scan_and_notify import scan_user, scan_all_users


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--user-id")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    init_db()

    if args.all:
        results = scan_all_users()
        for uid, ids in results.items():
            print(f"{uid}: created {len(ids)} proposals")
    else:
        ids = scan_user(args.user_id)
        print(f"Created {len(ids)} proposals for {args.user_id}: {ids}")


if __name__ == "__main__":
    main()

"""Seed the demo user (Jamie) into user_preferences.

Usage:
    uv run python scripts/seed_demo_user.py --user-id <your_telegram_user_id>

Note: Run google_oauth_setup.py FIRST to write google_tokens, OR run this first
and google_oauth_setup.py afterward — both paths work (upsert is idempotent and
preserves existing google_tokens).
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from src.db.schema import init_db
from src.db import dao


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args()

    init_db()
    existing = dao.get_user(args.user_id)
    google_tokens = existing.get("google_tokens") if existing else None

    dao.upsert_user({
        "telegram_user_id": args.user_id,
        "origin_city": "Singapore",
        "destinations": ["Japan", "South Korea", "Thailand"],
        "vague_preferences": "Loves the sea and mountains, enjoys slow relaxing trips with good food",
        "budget_per_person": 3000,
        "travelers": 1,
        "min_gap_days": 5,
        "price_drop_threshold": 20,
        "google_tokens": google_tokens,  # preserve if already set
    })
    user = dao.get_user(args.user_id)
    print(f"Seeded user {args.user_id}")
    print(f"  origin: {user['origin_city']}")
    print(f"  destinations: {user['destinations']}")
    print(f"  has google_tokens: {bool(user.get('google_tokens'))}")


if __name__ == "__main__":
    main()

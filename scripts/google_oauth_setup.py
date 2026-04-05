"""One-shot Google Calendar OAuth setup.

Run this ONCE per user before demo. It opens a browser, prompts for consent,
and writes the access_token + refresh_token into user_preferences.google_tokens.

Usage:
    cd backend
    uv run python ../scripts/google_oauth_setup.py --user-id <telegram_user_id>
"""

import argparse
import sys
from pathlib import Path

# Make backend/src importable when running from repo root
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from google_auth_oauthlib.flow import InstalledAppFlow

from src.db.schema import init_db
from src.db import dao

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
CLIENT_SECRET_PATH = BACKEND_DIR / "google_client_secret.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, help="Telegram user_id to attach tokens to")
    args = parser.parse_args()

    if not CLIENT_SECRET_PATH.exists():
        print(f"ERROR: {CLIENT_SECRET_PATH} not found. Download it from Google Cloud Console.")
        sys.exit(1)

    init_db()  # ensure tables exist

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    tokens = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }

    existing = dao.get_user(args.user_id)
    if existing is None:
        dao.upsert_user({"telegram_user_id": args.user_id, "google_tokens": tokens})
        print(f"Created new user_preferences row for {args.user_id} with tokens.")
    else:
        dao.update_user_google_tokens(args.user_id, tokens)
        print(f"Updated tokens for existing user {args.user_id}.")


if __name__ == "__main__":
    main()

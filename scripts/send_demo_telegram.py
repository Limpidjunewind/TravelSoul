"""Send a demo Telegram notification with a custom link (for live demo).

Usage:
    uv run python scripts/send_demo_telegram.py
    uv run python scripts/send_demo_telegram.py --link "http://localhost:3000/proposals/demo"
    uv run python scripts/send_demo_telegram.py --price-drop
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv
from telegram import Bot

load_dotenv(Path(__file__).resolve().parents[1] / "backend" / ".env")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
USER_ID = "6450091313"
DEFAULT_LINK = "http://localhost:3000/proposals/demo"

NEW_PROPOSAL_TMPL = (
    "\U0001f389 Hey Jamie! I've planned a trip for you.\n"
    "\U0001f4c5 Apr 18 – Apr 24 (7 days)\n"
    "\U0001f449 View details: {link}"
)

PRICE_DROP_TMPL = (
    "\U0001f4b0 Good news! Your trip (Apr 18 – Apr 24) just dropped 20%+\n"
    "\U0001f449 View details: {link}"
)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--link", default=DEFAULT_LINK)
    parser.add_argument("--price-drop", action="store_true")
    args = parser.parse_args()

    tmpl = PRICE_DROP_TMPL if args.price_drop else NEW_PROPOSAL_TMPL
    text = tmpl.format(link=args.link)

    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=USER_ID, text=text)
    print(f"Sent to {USER_ID}:\n{text}")


if __name__ == "__main__":
    asyncio.run(main())

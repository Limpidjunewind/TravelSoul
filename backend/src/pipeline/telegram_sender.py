"""Telegram push notifications (no bot interaction, push-only)."""

import asyncio
import os

from telegram import Bot


def _get_bot() -> Bot:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in environment.")
    return Bot(token=token)


async def _send_async(chat_id: str, text: str) -> None:
    bot = _get_bot()
    async with bot:
        await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=False)


def send_message(chat_id: str, text: str) -> None:
    """Synchronous wrapper for send_message. Safe to call from sync pipeline code."""
    asyncio.run(_send_async(chat_id, text))


def format_new_proposal_message(slot_start: str, slot_end: str, days: int, link: str) -> str:
    """Format the new-proposal push message per spec §8."""
    return (
        f"🎉 Hey! I've planned a trip for you.\n\n"
        f"📅 {slot_start} – {slot_end} ({days} days)\n\n"
        f"👉 View details: {link}"
    )


def format_price_drop_message(slot_start: str, slot_end: str, threshold_pct: int, link: str) -> str:
    """Format the confirmed-trip price-drop push message per spec §8."""
    return (
        f"💰 Good news! Your trip ({slot_start} – {slot_end}) just dropped {threshold_pct}%+\n\n"
        f"👉 View update: {link}"
    )

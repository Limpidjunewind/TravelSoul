"""Main proactive scan pipeline: find free slots, generate proposals, push notifications."""

import logging
import os
import uuid

from src.calendar_svc.client import fetch_events
from src.calendar_svc.slots import compute_free_slots
from src.db import dao
from src.pipeline.agent_runner import generate_proposal_bundle
from src.pipeline.telegram_sender import format_new_proposal_message, send_message

logger = logging.getLogger(__name__)


def _proposal_url(proposal_id: str) -> str:
    base = os.environ.get("PROPOSAL_URL_BASE", "https://nomie.app")
    return f"{base}/proposals/{proposal_id}"


def scan_user(telegram_user_id: str) -> list[str]:
    """Scan a single user's calendar and generate/push any new proposals.

    Returns list of proposal_ids created in this run.
    """
    user = dao.get_user(telegram_user_id)
    if user is None:
        logger.warning(f"User {telegram_user_id} not found, skipping.")
        return []
    if not user.get("google_tokens"):
        logger.warning(f"User {telegram_user_id} has no google_tokens, skipping.")
        return []

    logger.info(f"Scanning calendar for user {telegram_user_id}")
    events = fetch_events(telegram_user_id, days_ahead=60)
    logger.info(f"Fetched {len(events)} events")

    min_gap = user.get("min_gap_days") or 5
    slots = compute_free_slots(events, days_ahead=60, min_gap_days=min_gap)
    logger.info(f"Found {len(slots)} qualifying free slots")

    created_ids: list[str] = []
    for slot in slots:
        start_date = slot["start"].date().isoformat()
        end_date = slot["end"].date().isoformat()
        days = (slot["end"].date() - slot["start"].date()).days

        # Dedup: skip if already pending/rejected for this exact slot
        existing = dao.find_proposal_by_slot(telegram_user_id, start_date, end_date)
        if existing is not None:
            logger.info(f"Slot {start_date}..{end_date} already has proposal ({existing['status']}), skipping")
            continue

        logger.info(f"Generating bundle for slot {start_date}..{end_date}")
        bundle = generate_proposal_bundle(user, start_date, end_date, days)

        proposal_id = str(uuid.uuid4())
        dao.insert_proposal({
            "proposal_id": proposal_id,
            "telegram_user_id": telegram_user_id,
            "slot_start_date": start_date,
            "slot_end_date": end_date,
            "status": "pending",
            "bundle_data": bundle,
        })
        created_ids.append(proposal_id)
        logger.info(f"Inserted proposal {proposal_id}")

        # Push notification per spec §7 rule ①
        msg = format_new_proposal_message(
            slot_start=start_date,
            slot_end=end_date,
            days=days,
            link=_proposal_url(proposal_id),
        )
        try:
            send_message(telegram_user_id, msg)
            logger.info(f"Pushed Telegram notification for {proposal_id}")
        except Exception as e:
            logger.error(f"Failed to push Telegram for {proposal_id}: {e}")

    return created_ids


def scan_all_users() -> dict[str, list[str]]:
    """Scan every user in the DB. Returns mapping of user_id -> created proposal_ids."""
    users = dao.list_all_users()
    logger.info(f"Scanning {len(users)} users")
    out: dict[str, list[str]] = {}
    for u in users:
        try:
            out[u["telegram_user_id"]] = scan_user(u["telegram_user_id"])
        except Exception as e:
            logger.exception(f"Scan failed for user {u['telegram_user_id']}: {e}")
            out[u["telegram_user_id"]] = []
    return out

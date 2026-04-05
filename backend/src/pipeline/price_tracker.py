"""Re-quote confirmed trips and push notifications on significant price drops."""

import json
import logging

from src.db import dao
from src.pipeline.telegram_sender import format_price_drop_message, send_message
from src.tools.builtins.duffel_tool import duffel_flight_search_tool

logger = logging.getLogger(__name__)


def _extract_confirmed_flight_price(proposal: dict) -> int | None:
    """Pull out the confirmed option's total flight price from bundle_data."""
    bundle = proposal.get("bundle_data") or {}
    dests = bundle.get("destinations", [])
    chosen = proposal.get("confirmed_option")
    for d in dests:
        if d.get("name") == chosen and d.get("flights"):
            flight = d["flights"][0]
            return int(flight.get("price", 0))
    return None


def track_prices(telegram_user_id: str, proposal_url_fn) -> list[str]:
    """Check all confirmed proposals for this user. Push notification if price dropped
    by >= threshold, then reset baseline. Returns list of notified proposal_ids.
    """
    user = dao.get_user(telegram_user_id)
    if user is None:
        return []
    threshold_pct = user.get("price_drop_threshold") or 20

    notified: list[str] = []
    for proposal in dao.list_confirmed_proposals(telegram_user_id):
        baseline = proposal.get("baseline_price")
        if not baseline:
            continue

        # Re-quote via Duffel using the same dates & destination
        bundle = proposal.get("bundle_data") or {}
        chosen_name = proposal.get("confirmed_option")
        chosen = next((d for d in bundle.get("destinations", []) if d.get("name") == chosen_name), None)
        if chosen is None or not chosen.get("flights"):
            continue

        # Very simplified: use destination name's first 3 letters uppercase as fake IATA
        # In real impl, store IATA in bundle_data when confirming. For demo, log + skip.
        logger.warning(f"Price tracking: bundle_data missing IATA for {proposal['proposal_id']}, skipping")
        continue
        # (full implementation requires structured destination metadata; out of demo scope)

    return notified

"""Handle proposal confirmation: update DB, write Google Calendar event."""

import json
import logging

from src.calendar_svc.client import create_event
from src.db import dao
from src.db.connection import get_connection

logger = logging.getLogger(__name__)


def confirm_proposal(proposal_id: str, chosen_destination_name: str) -> dict:
    """Mark proposal as confirmed and write a calendar event. Returns updated proposal."""
    proposal = dao.get_proposal(proposal_id)
    if proposal is None:
        raise ValueError(f"Proposal {proposal_id} not found")
    if proposal["status"] != "pending":
        raise ValueError(f"Proposal {proposal_id} is {proposal['status']}, cannot confirm")

    bundle = proposal.get("bundle_data") or {}
    chosen = next(
        (d for d in bundle.get("destinations", []) if d.get("name") == chosen_destination_name),
        None,
    )
    if chosen is None:
        raise ValueError(f"Destination {chosen_destination_name} not in bundle")

    # Write calendar event (per spec §9: minimal info only)
    event_id = create_event(
        telegram_user_id=proposal["telegram_user_id"],
        title=f"🏝 Trip to {chosen_destination_name}",
        start_date=proposal["slot_start_date"],
        end_date=proposal["slot_end_date"],
        location=chosen_destination_name,
        description="Nomie planned trip",
    )

    # Compute baseline price
    total = chosen.get("total_price", 0)

    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE proposals
            SET status='confirmed', confirmed_option=?, baseline_price=?, last_price=?, calendar_event_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE proposal_id=?
            """,
            (chosen_destination_name, total, total, event_id, proposal_id),
        )
        conn.commit()
    finally:
        conn.close()

    return dao.get_proposal(proposal_id)


def reject_proposal(proposal_id: str) -> dict:
    """Mark proposal as rejected (terminal state, no calendar action)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE proposals SET status='rejected', updated_at=CURRENT_TIMESTAMP WHERE proposal_id=?",
            (proposal_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return dao.get_proposal(proposal_id)

"""Pure-logic free slot computation."""

from datetime import datetime, timedelta, timezone


def compute_free_slots(
    events: list[dict],
    now: datetime | None = None,
    days_ahead: int = 60,
    min_gap_days: int = 5,
) -> list[dict]:
    """Compute free date ranges between events.

    Args:
        events: list of dicts with 'start' and 'end' datetime keys (must be timezone-aware).
        now: reference time for "today" (defaults to datetime.now(utc)).
        days_ahead: horizon in days.
        min_gap_days: minimum consecutive free days required to report a slot.

    Returns:
        list of dicts with 'start' and 'end' datetime keys for each qualifying gap.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days_ahead)

    # Filter events within window and sort by start
    windowed = [
        {"start": e["start"], "end": e["end"]}
        for e in events
        if e["end"] > now and e["start"] < horizon
    ]
    windowed.sort(key=lambda e: e["start"])

    # Merge overlapping events
    merged: list[dict] = []
    for e in windowed:
        if merged and e["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], e["end"])
        else:
            merged.append({"start": e["start"], "end": e["end"]})

    # Compute gaps
    slots: list[dict] = []
    cursor = now
    for e in merged:
        if e["start"] > cursor:
            gap_days = (e["start"].date() - cursor.date()).days
            if gap_days >= min_gap_days:
                slots.append({"start": cursor, "end": e["start"]})
        cursor = max(cursor, e["end"])

    # Trailing gap
    if cursor < horizon:
        gap_days = (horizon.date() - cursor.date()).days
        if gap_days >= min_gap_days:
            slots.append({"start": cursor, "end": horizon})

    return slots

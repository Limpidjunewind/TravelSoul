from datetime import datetime, timedelta, timezone

from src.calendar_svc.slots import compute_free_slots


def _ev(start_day: int, end_day: int, base: datetime):
    return {
        "start": base + timedelta(days=start_day),
        "end": base + timedelta(days=end_day),
        "summary": "busy",
    }


def test_finds_single_large_gap():
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    events = [
        _ev(0, 1, base),    # Apr 1
        _ev(15, 16, base),  # Apr 15
    ]
    slots = compute_free_slots(events, now=base, days_ahead=30, min_gap_days=5)
    # Gap from Apr 2 to Apr 14 = 13 days (should be found)
    assert len(slots) >= 1
    found = any(s["start"].date() == (base + timedelta(days=1)).date() for s in slots)
    assert found


def test_ignores_gaps_shorter_than_min():
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    events = [
        _ev(0, 1, base),
        _ev(3, 4, base),    # only 2-day gap
        _ev(20, 21, base),  # 16-day gap after
    ]
    slots = compute_free_slots(events, now=base, days_ahead=30, min_gap_days=5)
    # Small gap (Apr 2-3) must not be returned
    for s in slots:
        gap_days = (s["end"].date() - s["start"].date()).days
        assert gap_days >= 5


def test_trailing_gap_until_horizon():
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    events = [_ev(0, 1, base)]
    slots = compute_free_slots(events, now=base, days_ahead=30, min_gap_days=5)
    # Should return trailing gap Apr 2 to Apr 30
    assert len(slots) >= 1
    last_slot = slots[-1]
    assert last_slot["end"].date() >= (base + timedelta(days=25)).date()


def test_no_events_returns_full_horizon():
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    slots = compute_free_slots([], now=base, days_ahead=30, min_gap_days=5)
    assert len(slots) == 1
    assert slots[0]["start"].date() == base.date()


def test_overlapping_events_merged():
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    events = [
        _ev(0, 3, base),
        _ev(2, 5, base),   # overlaps previous
        _ev(20, 21, base),
    ]
    slots = compute_free_slots(events, now=base, days_ahead=30, min_gap_days=5)
    # Gap should start at Apr 6 (after merged event ending Apr 5)
    assert len(slots) >= 1
    assert slots[0]["start"].date() == (base + timedelta(days=5)).date()

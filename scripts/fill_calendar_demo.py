"""Fill Google Calendar 2026-04-05..2026-06-04 with 'Busy' events, leaving 2026-04-18..2026-04-24 empty."""

from datetime import date, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from src.calendar_svc.client import create_event

USER_ID = "6450091313"
START = date(2026, 4, 5)
END = date(2026, 6, 4)
GAP_START = date(2026, 4, 18)
GAP_END = date(2026, 4, 24)

def main():
    d = START
    created = 0
    skipped = 0
    while d <= END:
        if GAP_START <= d <= GAP_END:
            skipped += 1
            d += timedelta(days=1)
            continue
        next_day = d + timedelta(days=1)
        try:
            create_event(
                telegram_user_id=USER_ID,
                title="Busy",
                start_date=d.isoformat(),
                end_date=next_day.isoformat(),
                location="",
                description="Demo placeholder",
            )
            created += 1
            print(f"  ✓ {d}")
        except Exception as e:
            print(f"  ✗ {d}: {e}")
        d += timedelta(days=1)
    print(f"\nDone. Created {created} events, skipped {skipped} (the 4/18-4/24 gap).")

if __name__ == "__main__":
    main()

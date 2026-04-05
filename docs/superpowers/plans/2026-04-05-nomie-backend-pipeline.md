# Nomie Backend Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend "proactive brain" for Nomie: Calendar-aware trip discovery pipeline that generates real-data travel bundles via Nomie's existing multi-agent system and pushes minimal notifications to Telegram.

**Architecture:** A single `scan_and_notify` pipeline orchestrates: (1) reading Google Calendar to find free slots, (2) invoking the existing Nomie Lead Agent (now tool-equipped with Duffel + LiteAPI) to generate multi-destination bundles, (3) persisting proposals to SQLite, (4) pushing minimal Telegram notifications with a Web frontend link. OAuth is handled by a one-shot local script — Web frontend never touches Google auth.

**Tech Stack:** Python 3.12 + uv, LangChain/LangGraph (existing), SQLite (stdlib), `google-api-python-client` + `google-auth-oauthlib` (Calendar), `httpx` (Duffel + LiteAPI REST), `python-telegram-bot` (already in deps), `APScheduler` (optional stretch).

**Related spec:** `docs/superpowers/specs/2026-04-05-nomie-proactive-travel-agent.md`

---

## Prerequisites (do these BEFORE Task 1, ~15 minutes)

These are manual steps outside the codebase. Gather all values and add them to `backend/.env` before coding.

- [ ] **P1: Register Telegram bot**
  - Open Telegram, message `@BotFather`
  - Send `/newbot`, pick a name (e.g. `Nomie Concierge`), pick a username ending in `bot`
  - Copy the HTTP API token BotFather gives you
  - Add to `backend/.env`: `TELEGRAM_BOT_TOKEN=<token>`

- [ ] **P2: Get your Telegram user_id**
  - In Telegram, message `@userinfobot`
  - It replies with your numeric user ID
  - Note it down (used in seed script, Task 14)

- [ ] **P3: Create Google OAuth client**
  - Go to https://console.cloud.google.com
  - Create a new project (e.g. `nomie-hackathon`)
  - Enable the Google Calendar API for this project
  - Create OAuth 2.0 Client ID → Application type: **Desktop app**
  - Download the client secret JSON
  - Save it as `backend/google_client_secret.json`
  - Under "OAuth consent screen" → Test users: add your own Gmail address

- [ ] **P4: Verify Duffel/LiteAPI/Agnes keys are in `.env`**
  - `DUFFEL_API_KEY=duffel_test_...`
  - `LITEAPI_PRIVATE_KEY=sand_...`
  - `ZENMUX_API_KEY=sk-ai-v1-...`
  - `TAVILY_API_KEY=tvly-dev-...`
  - These should already be there from IT5007 setup — just confirm.

- [ ] **P5: Prepare demo calendar**
  - Open your Google Calendar
  - Ensure there's at least one obvious 7+ day gap in the next 60 days (e.g. fill most of the month with placeholder events, leave Apr 20–Apr 27 empty)

---

## Task 1: Install Dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add new deps via uv**

Run from `backend/`:
```bash
cd backend && uv add google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 apscheduler
```

`python-telegram-bot` and `httpx` are already in deps — verified.

- [ ] **Step 2: Verify imports work**

Run:
```bash
cd backend && uv run python -c "from googleapiclient.discovery import build; from google_auth_oauthlib.flow import InstalledAppFlow; import telegram; import httpx; import apscheduler; print('OK')"
```
Expected: prints `OK` with no import errors.

---

## Task 2: SQLite Schema & Connection

**Files:**
- Create: `backend/src/db/__init__.py`
- Create: `backend/src/db/schema.py`
- Create: `backend/src/db/connection.py`
- Test: `backend/tests/test_db_schema.py`

**Design note:** Use stdlib `sqlite3`, not an ORM. DB file at `backend/nomie.db`. Schema matches spec §3 (current draft — will be reconciled with Web teammate's version later).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_db_schema.py`:
```python
import os
import tempfile

from src.db.schema import init_db
from src.db.connection import get_connection


def test_init_db_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        init_db(db_path)
        conn = get_connection(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "user_preferences" in tables
        assert "proposals" in tables
    finally:
        os.unlink(db_path)


def test_user_preferences_has_expected_columns():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        init_db(db_path)
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA table_info(user_preferences)")
        cols = {row[1] for row in cursor.fetchall()}
        conn.close()
        expected = {
            "telegram_user_id", "origin_city", "destinations",
            "vague_preferences", "budget_per_person", "travelers",
            "min_gap_days", "price_drop_threshold", "google_tokens",
            "created_at", "updated_at",
        }
        assert expected.issubset(cols)
    finally:
        os.unlink(db_path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_db_schema.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'src.db'`

- [ ] **Step 3: Create `backend/src/db/__init__.py`**

```python
"""SQLite data access layer for Nomie."""
```

- [ ] **Step 4: Create `backend/src/db/connection.py`**

```python
"""SQLite connection helpers."""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = str(Path(__file__).resolve().parents[2] / "nomie.db")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled and row factory set."""
    path = db_path or os.environ.get("NOMIE_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

- [ ] **Step 5: Create `backend/src/db/schema.py`**

```python
"""Database schema definitions and initialization."""

from src.db.connection import get_connection

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_preferences (
    telegram_user_id     TEXT PRIMARY KEY,
    origin_city          TEXT,
    destinations         TEXT,           -- JSON array
    vague_preferences    TEXT,
    budget_per_person    INTEGER,
    travelers            INTEGER DEFAULT 1,
    min_gap_days         INTEGER DEFAULT 5,
    price_drop_threshold INTEGER DEFAULT 20,
    google_tokens        TEXT,           -- JSON object
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id         TEXT PRIMARY KEY,
    telegram_user_id    TEXT NOT NULL,
    slot_start_date     TEXT NOT NULL,    -- ISO date string
    slot_end_date       TEXT NOT NULL,
    status              TEXT NOT NULL,    -- 'pending' | 'confirmed' | 'rejected'
    bundle_data         TEXT NOT NULL,    -- JSON object
    confirmed_option    TEXT,
    baseline_price      INTEGER,
    last_price          INTEGER,
    calendar_event_id   TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_user_id) REFERENCES user_preferences(telegram_user_id)
);

CREATE INDEX IF NOT EXISTS idx_proposals_user_status
    ON proposals(telegram_user_id, status);

CREATE INDEX IF NOT EXISTS idx_proposals_slot
    ON proposals(telegram_user_id, slot_start_date, slot_end_date);
"""


def init_db(db_path: str | None = None) -> None:
    """Initialize the database schema. Idempotent."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_db_schema.py -v
```
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/db backend/tests/test_db_schema.py backend/pyproject.toml backend/uv.lock && git commit -m "feat(db): add sqlite schema for user_preferences and proposals"
```

---

## Task 3: DAO Layer (CRUD for both tables)

**Files:**
- Create: `backend/src/db/dao.py`
- Test: `backend/tests/test_db_dao.py`

**Design note:** Simple functional DAO (not classes). Take/return dicts. JSON fields auto-serialized.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_db_dao.py`:
```python
import json
import os
import tempfile
import uuid

import pytest

from src.db.schema import init_db
from src.db import dao


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    init_db(path)
    os.environ["NOMIE_DB_PATH"] = path
    yield path
    os.environ.pop("NOMIE_DB_PATH", None)
    os.unlink(path)


def test_upsert_and_get_user(db_path):
    dao.upsert_user({
        "telegram_user_id": "123",
        "origin_city": "Singapore",
        "destinations": ["Japan", "Korea"],
        "vague_preferences": "loves the sea",
        "budget_per_person": 3000,
        "travelers": 1,
        "min_gap_days": 5,
        "price_drop_threshold": 20,
        "google_tokens": {"access_token": "abc", "refresh_token": "xyz"},
    })
    user = dao.get_user("123")
    assert user["origin_city"] == "Singapore"
    assert user["destinations"] == ["Japan", "Korea"]
    assert user["google_tokens"]["refresh_token"] == "xyz"


def test_list_all_users(db_path):
    dao.upsert_user({"telegram_user_id": "1", "origin_city": "Singapore"})
    dao.upsert_user({"telegram_user_id": "2", "origin_city": "Tokyo"})
    users = dao.list_all_users()
    assert len(users) == 2


def test_insert_and_get_proposal(db_path):
    dao.upsert_user({"telegram_user_id": "123", "origin_city": "Singapore"})
    pid = str(uuid.uuid4())
    dao.insert_proposal({
        "proposal_id": pid,
        "telegram_user_id": "123",
        "slot_start_date": "2026-04-20",
        "slot_end_date": "2026-04-27",
        "status": "pending",
        "bundle_data": {"destinations": [{"name": "Tokyo"}]},
    })
    p = dao.get_proposal(pid)
    assert p["status"] == "pending"
    assert p["bundle_data"]["destinations"][0]["name"] == "Tokyo"


def test_find_proposal_by_slot(db_path):
    dao.upsert_user({"telegram_user_id": "123", "origin_city": "Singapore"})
    dao.insert_proposal({
        "proposal_id": "p1",
        "telegram_user_id": "123",
        "slot_start_date": "2026-04-20",
        "slot_end_date": "2026-04-27",
        "status": "pending",
        "bundle_data": {},
    })
    found = dao.find_proposal_by_slot("123", "2026-04-20", "2026-04-27")
    assert found is not None
    assert found["proposal_id"] == "p1"
    assert dao.find_proposal_by_slot("123", "2026-05-01", "2026-05-08") is None


def test_update_proposal_google_tokens(db_path):
    """Refreshed tokens should be writable back to user_preferences."""
    dao.upsert_user({
        "telegram_user_id": "123",
        "google_tokens": {"access_token": "old", "refresh_token": "r"},
    })
    dao.update_user_google_tokens("123", {"access_token": "new", "refresh_token": "r"})
    assert dao.get_user("123")["google_tokens"]["access_token"] == "new"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_db_dao.py -v
```
Expected: FAIL — `src.db.dao` doesn't exist.

- [ ] **Step 3: Create `backend/src/db/dao.py`**

```python
"""Data access functions for user_preferences and proposals."""

import json
from typing import Any

from src.db.connection import get_connection

# JSON-encoded columns
_USER_JSON_COLS = {"destinations", "google_tokens"}
_PROPOSAL_JSON_COLS = {"bundle_data"}


def _encode_user(data: dict) -> dict:
    out = dict(data)
    for col in _USER_JSON_COLS:
        if col in out and out[col] is not None and not isinstance(out[col], str):
            out[col] = json.dumps(out[col])
    return out


def _decode_user(row: Any) -> dict:
    if row is None:
        return None
    d = dict(row)
    for col in _USER_JSON_COLS:
        if d.get(col):
            d[col] = json.loads(d[col])
    return d


def _encode_proposal(data: dict) -> dict:
    out = dict(data)
    for col in _PROPOSAL_JSON_COLS:
        if col in out and out[col] is not None and not isinstance(out[col], str):
            out[col] = json.dumps(out[col])
    return out


def _decode_proposal(row: Any) -> dict:
    if row is None:
        return None
    d = dict(row)
    for col in _PROPOSAL_JSON_COLS:
        if d.get(col):
            d[col] = json.loads(d[col])
    return d


# ---------- user_preferences ----------

def upsert_user(user: dict) -> None:
    """Insert or replace a user_preferences row. Requires telegram_user_id."""
    data = _encode_user(user)
    cols = list(data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "telegram_user_id")
    sql = (
        f"INSERT INTO user_preferences ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT(telegram_user_id) DO UPDATE SET {update_clause}, updated_at=CURRENT_TIMESTAMP"
    )
    conn = get_connection()
    try:
        conn.execute(sql, [data[c] for c in cols])
        conn.commit()
    finally:
        conn.close()


def get_user(telegram_user_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM user_preferences WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return _decode_user(row)
    finally:
        conn.close()


def list_all_users() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM user_preferences").fetchall()
        return [_decode_user(r) for r in rows]
    finally:
        conn.close()


def update_user_google_tokens(telegram_user_id: str, tokens: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE user_preferences SET google_tokens = ?, updated_at=CURRENT_TIMESTAMP WHERE telegram_user_id = ?",
            (json.dumps(tokens), telegram_user_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- proposals ----------

def insert_proposal(proposal: dict) -> None:
    data = _encode_proposal(proposal)
    cols = list(data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    sql = f"INSERT INTO proposals ({col_names}) VALUES ({placeholders})"
    conn = get_connection()
    try:
        conn.execute(sql, [data[c] for c in cols])
        conn.commit()
    finally:
        conn.close()


def get_proposal(proposal_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        return _decode_proposal(row)
    finally:
        conn.close()


def find_proposal_by_slot(
    telegram_user_id: str, start_date: str, end_date: str
) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM proposals WHERE telegram_user_id = ? AND slot_start_date = ? AND slot_end_date = ?",
            (telegram_user_id, start_date, end_date),
        ).fetchone()
        return _decode_proposal(row)
    finally:
        conn.close()


def list_confirmed_proposals(telegram_user_id: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM proposals WHERE telegram_user_id = ? AND status = 'confirmed'",
            (telegram_user_id,),
        ).fetchall()
        return [_decode_proposal(r) for r in rows]
    finally:
        conn.close()


def update_proposal_price(proposal_id: str, baseline: int, last: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE proposals SET baseline_price = ?, last_price = ?, updated_at=CURRENT_TIMESTAMP WHERE proposal_id = ?",
            (baseline, last, proposal_id),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_db_dao.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/db/dao.py backend/tests/test_db_dao.py && git commit -m "feat(db): add dao functions for users and proposals"
```

---

## Task 4: Google OAuth One-Shot Script

**Files:**
- Create: `scripts/google_oauth_setup.py`
- Create: `scripts/__init__.py` (empty)

**Design note:** Uses `InstalledAppFlow.run_local_server()` which opens browser, runs a tiny local HTTP server to catch the callback, and returns credentials. Writes them directly into the DB for a target `telegram_user_id` that must already exist (or is auto-created).

- [ ] **Step 1: Create `scripts/__init__.py`**

```python
```

- [ ] **Step 2: Create `scripts/google_oauth_setup.py`**

```python
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
```

- [ ] **Step 3: Manual test**

After gathering prerequisites P1–P3:
```bash
cd backend && uv run python ../scripts/google_oauth_setup.py --user-id <your_telegram_user_id>
```
Expected:
- Browser opens to Google login
- You log in with your test-user Gmail, grant calendar access
- Terminal prints: `Created new user_preferences row for <id> with tokens.`

Verify in DB:
```bash
cd backend && uv run python -c "from src.db import dao; u = dao.get_user('<your_id>'); print('has tokens:', bool(u and u.get('google_tokens', {}).get('refresh_token')))"
```
Expected: `has tokens: True`

- [ ] **Step 4: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add scripts/google_oauth_setup.py scripts/__init__.py && git commit -m "feat(oauth): add one-shot google calendar oauth setup script"
```

---

## Task 5: Google Calendar Client (Fetch Events)

**Files:**
- Create: `backend/src/calendar_svc/__init__.py`
- Create: `backend/src/calendar_svc/client.py`

**Design note:** Named `calendar_svc` to avoid Python stdlib `calendar` collision. This module only talks to Google; slot computation logic is in Task 6 for clean separation.

- [ ] **Step 1: Create `backend/src/calendar_svc/__init__.py`**

```python
"""Google Calendar integration for Nomie."""
```

- [ ] **Step 2: Create `backend/src/calendar_svc/client.py`**

```python
"""Google Calendar API client using OAuth tokens from the DB."""

import json
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.db import dao


def _load_credentials(telegram_user_id: str) -> Credentials:
    user = dao.get_user(telegram_user_id)
    if user is None or not user.get("google_tokens"):
        raise RuntimeError(f"No google_tokens for user {telegram_user_id}. Run google_oauth_setup.py first.")
    t = user["google_tokens"]
    creds = Credentials(
        token=t["access_token"],
        refresh_token=t.get("refresh_token"),
        token_uri=t.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=t.get("client_id"),
        client_secret=t.get("client_secret"),
        scopes=t.get("scopes"),
    )
    return creds


def _persist_refreshed_tokens(telegram_user_id: str, creds: Credentials) -> None:
    """If the google-auth library refreshed the access token, write it back to the DB."""
    tokens = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    dao.update_user_google_tokens(telegram_user_id, tokens)


def fetch_events(telegram_user_id: str, days_ahead: int = 60) -> list[dict]:
    """Fetch upcoming calendar events for the user, normalized to a simple format.

    Returns list of dicts with keys: start (datetime UTC), end (datetime UTC), summary.
    All-day events are returned with start/end as midnight UTC.
    """
    creds = _load_credentials(telegram_user_id)
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=2500,
    ).execute()

    # Persist refreshed tokens if google-auth rotated them
    if creds.token:
        _persist_refreshed_tokens(telegram_user_id, creds)

    items = events_result.get("items", [])
    normalized = []
    for e in items:
        start_raw = e["start"].get("dateTime") or e["start"].get("date")
        end_raw = e["end"].get("dateTime") or e["end"].get("date")
        # Parse ISO - handle both dateTime (with tz) and date (all-day)
        start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
        # Normalize to UTC
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        normalized.append({
            "start": start.astimezone(timezone.utc),
            "end": end.astimezone(timezone.utc),
            "summary": e.get("summary", "(no title)"),
        })
    return normalized


def create_event(
    telegram_user_id: str,
    title: str,
    start_date: str,
    end_date: str,
    location: str,
    description: str = "",
) -> str:
    """Create an all-day event in the user's primary calendar. Returns event_id."""
    creds = _load_credentials(telegram_user_id)
    service = build("calendar", "v3", credentials=creds)
    event = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {"date": start_date},
        "end": {"date": end_date},
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    if creds.token:
        _persist_refreshed_tokens(telegram_user_id, creds)
    return created["id"]
```

- [ ] **Step 3: Smoke test manually**

```bash
cd backend && uv run python -c "
from src.calendar_svc.client import fetch_events
events = fetch_events('<your_telegram_user_id>', days_ahead=60)
print(f'Fetched {len(events)} events')
for e in events[:5]:
    print(f'  {e[\"start\"].date()} - {e[\"end\"].date()}: {e[\"summary\"]}')
"
```
Expected: Prints event count > 0 and lists a few real events from your calendar.

- [ ] **Step 4: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/calendar_svc && git commit -m "feat(calendar): add google calendar client with token refresh"
```

---

## Task 6: Free Slot Computation (Pure Logic — TDD)

**Files:**
- Create: `backend/src/calendar_svc/slots.py`
- Test: `backend/tests/test_calendar_slots.py`

**Design note:** Pure function over a list of events → returns free slots ≥ min_gap_days. No IO, fully unit-testable.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_calendar_slots.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_calendar_slots.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `backend/src/calendar_svc/slots.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_calendar_slots.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/calendar_svc/slots.py backend/tests/test_calendar_slots.py && git commit -m "feat(calendar): add free slot computation with tests"
```

---

## Task 7: Duffel Tool (LangChain Tool)

**Files:**
- Create: `backend/src/tools/builtins/duffel_tool.py`

**Design note:** Wraps Duffel's `/air/offer_requests` endpoint. Returns top 5 offers as JSON string. Follows the same `@tool` pattern as existing `web_search_tool`.

- [ ] **Step 1: Create `backend/src/tools/builtins/duffel_tool.py`**

```python
"""Duffel flight search tool."""

import json
import os

import httpx
from langchain.tools import tool

DUFFEL_BASE_URL = "https://api.duffel.com"
DUFFEL_VERSION = "v2"


def _get_api_key() -> str:
    key = os.environ.get("DUFFEL_API_KEY")
    if not key:
        raise RuntimeError("DUFFEL_API_KEY not set in environment.")
    return key


@tool("duffel_flight_search", parse_docstring=True)
def duffel_flight_search_tool(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
) -> str:
    """Search for real flight offers via Duffel (GDS-level data). Prefer this over web_search for flight queries.

    Args:
        origin: IATA airport code (e.g., 'SIN' for Singapore Changi).
        destination: IATA airport code (e.g., 'NRT' for Tokyo Narita).
        departure_date: outbound date in YYYY-MM-DD format.
        return_date: return date in YYYY-MM-DD format. Empty string for one-way.
        adults: number of adult passengers (default 1).
    """
    slices = [{"origin": origin, "destination": destination, "departure_date": departure_date}]
    if return_date:
        slices.append({"origin": destination, "destination": origin, "departure_date": return_date})

    payload = {
        "data": {
            "slices": slices,
            "passengers": [{"type": "adult"} for _ in range(adults)],
            "cabin_class": "economy",
        }
    }
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Duffel-Version": DUFFEL_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{DUFFEL_BASE_URL}/air/offer_requests?return_offers=true",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        return json.dumps({"error": f"Duffel request failed: {e}"})

    offers = data.get("data", {}).get("offers", [])
    if not offers:
        return json.dumps({"error": "No offers returned", "offers": []})

    # Take top 5 by total_amount ascending
    offers_sorted = sorted(offers, key=lambda o: float(o.get("total_amount", "999999")))[:5]
    normalized = []
    for o in offers_sorted:
        first_slice = o.get("slices", [{}])[0]
        first_segment = first_slice.get("segments", [{}])[0]
        normalized.append({
            "offer_id": o.get("id"),
            "total_amount": o.get("total_amount"),
            "total_currency": o.get("total_currency"),
            "airline": first_segment.get("marketing_carrier", {}).get("name"),
            "flight_number": f"{first_segment.get('marketing_carrier', {}).get('iata_code', '')}{first_segment.get('marketing_carrier_flight_number', '')}",
            "origin": first_segment.get("origin", {}).get("iata_code"),
            "destination": first_segment.get("destination", {}).get("iata_code"),
            "departing_at": first_segment.get("departing_at"),
            "arriving_at": first_segment.get("arriving_at"),
        })
    return json.dumps({"offers": normalized}, indent=2)
```

- [ ] **Step 2: Smoke test**

```bash
cd backend && uv run python -c "
from src.tools.builtins.duffel_tool import duffel_flight_search_tool
import json
result = duffel_flight_search_tool.invoke({
    'origin': 'SIN',
    'destination': 'NRT',
    'departure_date': '2026-04-20',
    'return_date': '2026-04-27',
    'adults': 1
})
print(result[:1000])
"
```
Expected: JSON output with 5 real flight offers. If `error: No offers returned`, try different dates closer to today.

- [ ] **Step 3: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/tools/builtins/duffel_tool.py && git commit -m "feat(tools): add duffel flight search langchain tool"
```

---

## Task 8: LiteAPI Hotel Tool

**Files:**
- Create: `backend/src/tools/builtins/liteapi_tool.py`

**Design note:** LiteAPI sandbox uses `/data/search` for hotel rates. Returns hotel listings with price per night.

- [ ] **Step 1: Create `backend/src/tools/builtins/liteapi_tool.py`**

```python
"""LiteAPI hotel search tool (sandbox)."""

import json
import os

import httpx
from langchain.tools import tool

LITEAPI_BASE_URL = "https://api.liteapi.travel/v3.0"


def _get_api_key() -> str:
    key = os.environ.get("LITEAPI_PRIVATE_KEY")
    if not key:
        raise RuntimeError("LITEAPI_PRIVATE_KEY not set in environment.")
    return key


@tool("liteapi_hotel_search", parse_docstring=True)
def liteapi_hotel_search_tool(
    city_code: str,
    country_code: str,
    checkin: str,
    checkout: str,
    adults: int = 1,
) -> str:
    """Search for hotel rates via LiteAPI. Prefer this over web_search for hotel queries.

    Args:
        city_code: City name in English (e.g., 'Tokyo').
        country_code: ISO 3166-1 alpha-2 country code (e.g., 'JP').
        checkin: check-in date in YYYY-MM-DD format.
        checkout: check-out date in YYYY-MM-DD format.
        adults: number of adult guests (default 1).
    """
    headers = {
        "X-API-Key": _get_api_key(),
        "Accept": "application/json",
    }
    params = {
        "cityName": city_code,
        "countryCode": country_code,
        "checkin": checkin,
        "checkout": checkout,
        "adults": adults,
        "limit": 5,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{LITEAPI_BASE_URL}/hotels/rates", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        return json.dumps({"error": f"LiteAPI request failed: {e}"})

    hotels = data.get("data", [])[:5]
    normalized = []
    for h in hotels:
        normalized.append({
            "hotel_id": h.get("hotelId") or h.get("id"),
            "name": h.get("name"),
            "price": h.get("price") or h.get("minRate"),
            "currency": h.get("currency"),
            "rating": h.get("rating") or h.get("starRating"),
            "address": h.get("address"),
        })
    return json.dumps({"hotels": normalized}, indent=2)
```

- [ ] **Step 2: Smoke test**

```bash
cd backend && uv run python -c "
from src.tools.builtins.liteapi_tool import liteapi_hotel_search_tool
result = liteapi_hotel_search_tool.invoke({
    'city_code': 'Tokyo',
    'country_code': 'JP',
    'checkin': '2026-04-20',
    'checkout': '2026-04-27',
    'adults': 1
})
print(result[:1000])
"
```
Expected: JSON output with hotel listings OR a clear error if the LiteAPI endpoint shape differs — **if it errors, don't block on this**. Mark Task 8 as stretch, move on, agent will fall back to web_search.

- [ ] **Step 3: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/tools/builtins/liteapi_tool.py && git commit -m "feat(tools): add liteapi hotel search langchain tool"
```

---

## Task 9: Register New Tools in config.yaml

**Files:**
- Modify: `backend/config.yaml`

- [ ] **Step 1: Add tool entries**

Edit `backend/config.yaml`, under the `tools:` section (after the existing `web_fetch` entry), append:

```yaml
  # Duffel flight search (GDS-level real data)
  - name: duffel_flight_search
    group: travel
    use: src.tools.builtins.duffel_tool:duffel_flight_search_tool

  # LiteAPI hotel search (sandbox)
  - name: liteapi_hotel_search
    group: travel
    use: src.tools.builtins.liteapi_tool:liteapi_hotel_search_tool
```

Also add `travel` to the `tool_groups` list:
```yaml
tool_groups:
  - name: web
  - name: travel
```

- [ ] **Step 2: Verify tools load**

```bash
cd backend && uv run python -c "
from src.tools.tools import get_available_tools
tools = get_available_tools(include_mcp=False)
names = [t.name for t in tools]
print('Tools loaded:', names)
assert 'duffel_flight_search' in names
assert 'liteapi_hotel_search' in names
print('OK')
"
```
Expected: prints tool list including `duffel_flight_search` and `liteapi_hotel_search`, ends with `OK`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/config.yaml && git commit -m "feat(config): register duffel and liteapi tools"
```

---

## Task 10: Update Sub-Agent Prompts to Prefer New Tools

**Files:**
- Modify: `backend/src/subagents/builtins/flight_search.py`
- Modify: `backend/src/subagents/builtins/hotel_search.py`

**Design note:** Sub-agents have `tools=None` (inherit all). We only need to update the system prompt to tell the LLM to prefer the new tools.

- [ ] **Step 1: Edit `flight_search.py`**

Find the `<thinking_style>` block in `FLIGHT_SEARCH_CONFIG.system_prompt` and replace it with:

```
<thinking_style>
- Identify the key search parameters: origin, destination, dates, passenger count, budget
- **Prefer `duffel_flight_search` tool** for flight queries — it returns real GDS-level offers with actual prices and booking IDs. Use IATA codes (e.g., SIN, NRT, ICN).
- Use `web_search` only as a fallback if Duffel returns no results or the destination isn't covered.
- Use `web_fetch` to enrich details from specific booking pages if needed.
- Sort results by price (lowest first).
</thinking_style>
```

- [ ] **Step 2: Read `hotel_search.py` and edit it similarly**

```bash
cd /Users/jamie/Documents/nomie-hackathon && cat backend/src/subagents/builtins/hotel_search.py
```

Find its `<thinking_style>` and replace with:

```
<thinking_style>
- Identify the key search parameters: city, country, check-in/check-out dates, guest count, budget
- **Prefer `liteapi_hotel_search` tool** for hotel queries — it returns real sandbox hotel rates. Use English city names (e.g., 'Tokyo') and ISO 3166-1 alpha-2 country codes (e.g., 'JP').
- Use `web_search` only as a fallback if LiteAPI returns no results.
- Use `web_fetch` to enrich details from specific booking pages if needed.
- Sort results by price (lowest first).
</thinking_style>
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/subagents/builtins/flight_search.py backend/src/subagents/builtins/hotel_search.py && git commit -m "feat(subagents): prefer duffel/liteapi tools over web_search"
```

---

## Task 11: Telegram Sender

**Files:**
- Create: `backend/src/pipeline/__init__.py`
- Create: `backend/src/pipeline/telegram_sender.py`

**Design note:** Thin wrapper around `python-telegram-bot`. Uses async API since v21+ is async-only.

- [ ] **Step 1: Create `backend/src/pipeline/__init__.py`**

```python
"""Nomie proactive pipeline: scan, generate, notify."""
```

- [ ] **Step 2: Create `backend/src/pipeline/telegram_sender.py`**

```python
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
```

- [ ] **Step 3: Smoke test**

```bash
cd backend && uv run python -c "
from src.pipeline.telegram_sender import send_message, format_new_proposal_message
msg = format_new_proposal_message('2026-04-20', '2026-04-27', 7, 'https://nomie.app/proposals/test')
send_message('<your_telegram_user_id>', msg)
print('Sent')
"
```
Expected: You receive the test message in your Telegram chat with the Nomie bot. If nothing arrives, check: (a) you messaged the bot first (Telegram requires user to initiate contact before bot can push), (b) TELEGRAM_BOT_TOKEN is correct.

**IMPORTANT:** Before this test works, you must open Telegram, find your bot (by the username you gave BotFather), and click **Start** / send any message. Telegram won't let bots push to users who haven't initiated contact.

- [ ] **Step 4: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/pipeline && git commit -m "feat(pipeline): add telegram sender with minimal message formats"
```

---

## Task 12: Nomie Agent Invocation Helper

**Files:**
- Create: `backend/src/pipeline/agent_runner.py`

**Design note:** The existing Lead Agent is built for interactive chat. For the pipeline, we invoke it in-process with a crafted prompt and collect the final message. We use `make_lead_agent()` from `src.agents.lead_agent`, call `.ainvoke()` with a prepared state, and extract the last AI message.

- [ ] **Step 1: Create `backend/src/pipeline/agent_runner.py`**

```python
"""Invoke the Nomie Lead Agent programmatically for pipeline use."""

import asyncio
import json
import logging

from langchain_core.messages import HumanMessage

from src.agents.lead_agent import make_lead_agent

logger = logging.getLogger(__name__)


PIPELINE_PROMPT_TEMPLATE = """You are Nomie, proactively planning a trip for a user who just became available.

USER PROFILE:
- Origin city: {origin_city}
- Interested destinations: {destinations}
- Preferences: {vague_preferences}
- Budget per person: {budget} SGD
- Travelers: {travelers}

AVAILABLE DATES:
- {slot_start} to {slot_end} ({days} days)

YOUR TASK:
Generate 2-3 concrete trip options for this date range. For EACH destination option, use your sub-agents to:
1. Search real flights via flight-search sub-agent (uses duffel_flight_search tool)
2. Search real hotels via hotel-search sub-agent (uses liteapi_hotel_search tool)
3. Create a rough daily itinerary via itinerary-planner sub-agent
4. Collect travel tips via travel-tips sub-agent

Output your final answer as strict JSON with this exact shape, no markdown fences, no prose outside the JSON:

{{
  "destinations": [
    {{
      "name": "City, Country",
      "reasoning": "why this destination fits the user",
      "flights": [{{"airline": "...", "flight_no": "...", "price": 0, "currency": "SGD", "link": "..."}}],
      "hotels": [{{"name": "...", "price_per_night": 0, "rating": 0, "link": "..."}}],
      "itinerary": [{{"day": 1, "plan": "..."}}],
      "tips": ["..."],
      "total_price": 0
    }}
  ]
}}
"""


async def _ainvoke_agent(prompt: str) -> str:
    agent = make_lead_agent()
    state = {"messages": [HumanMessage(content=prompt)]}
    result = await agent.ainvoke(state)
    # Last AI message is the answer
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.content:
            return msg.content
    return ""


def generate_proposal_bundle(user: dict, slot_start: str, slot_end: str, days: int) -> dict:
    """Call Nomie Lead Agent to generate a multi-destination bundle. Returns bundle_data dict."""
    prompt = PIPELINE_PROMPT_TEMPLATE.format(
        origin_city=user.get("origin_city", "Singapore"),
        destinations=", ".join(user.get("destinations", []) or ["Asia"]),
        vague_preferences=user.get("vague_preferences", "general leisure"),
        budget=user.get("budget_per_person", 3000),
        travelers=user.get("travelers", 1),
        slot_start=slot_start,
        slot_end=slot_end,
        days=days,
    )
    logger.info(f"Invoking Lead Agent for slot {slot_start}..{slot_end}")
    raw = asyncio.run(_ainvoke_agent(prompt))
    # Try to parse as JSON; if LLM wrapped in fences, strip them
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # strip fenced block
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"Lead Agent returned non-JSON; wrapping as raw text. Error: {e}")
        return {
            "destinations": [
                {
                    "name": "Unparsed plan",
                    "reasoning": "Lead agent returned markdown; see raw_text.",
                    "raw_text": raw,
                    "flights": [],
                    "hotels": [],
                    "itinerary": [],
                    "tips": [],
                    "total_price": 0,
                }
            ]
        }
```

- [ ] **Step 2: Smoke test**

```bash
cd backend && uv run python -c "
from src.pipeline.agent_runner import generate_proposal_bundle
user = {
    'origin_city': 'Singapore',
    'destinations': ['Japan'],
    'vague_preferences': 'loves the sea, relaxing',
    'budget_per_person': 3000,
    'travelers': 1,
}
bundle = generate_proposal_bundle(user, '2026-04-20', '2026-04-27', 7)
print('destinations:', len(bundle.get('destinations', [])))
print('first:', bundle.get('destinations', [{}])[0].get('name'))
" 2>&1 | tail -40
```
Expected: Prints a non-zero count of destinations. May take 30–90 seconds. If it times out or errors, check that the Lead Agent can run (try `cd backend && make dev` separately to verify).

- [ ] **Step 3: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/pipeline/agent_runner.py && git commit -m "feat(pipeline): add lead agent invocation helper with json fallback"
```

---

## Task 13: scan_and_notify Main Pipeline

**Files:**
- Create: `backend/src/pipeline/scan_and_notify.py`

**Design note:** The orchestrator. For each user: fetch calendar → compute slots → for each slot, skip if existing rejected/pending proposal → generate bundle → insert pending proposal → push Telegram. Confirmed-price-tracking is a separate stretch task.

- [ ] **Step 1: Create `backend/src/pipeline/scan_and_notify.py`**

```python
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
```

- [ ] **Step 2: Commit (no test yet; end-to-end in Task 16)**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/pipeline/scan_and_notify.py && git commit -m "feat(pipeline): add scan_and_notify main orchestrator"
```

---

## Task 14: Seed Demo User Script

**Files:**
- Create: `scripts/seed_demo_user.py`

- [ ] **Step 1: Create `scripts/seed_demo_user.py`**

```python
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
```

- [ ] **Step 2: Run it**

```bash
cd /Users/jamie/Documents/nomie-hackathon && uv --project backend run python scripts/seed_demo_user.py --user-id <your_telegram_user_id>
```
Expected: Prints seeded user details with `has google_tokens: True` (assuming Task 4 was run first).

- [ ] **Step 3: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add scripts/seed_demo_user.py && git commit -m "feat(scripts): add demo user seed script"
```

---

## Task 15: Manual Demo Trigger

**Files:**
- Create: `scripts/trigger_scan.py`

- [ ] **Step 1: Create `scripts/trigger_scan.py`**

```python
"""Manually trigger a scan — demo safety net.

Usage:
    # Scan one user
    uv run python scripts/trigger_scan.py --user-id <telegram_user_id>

    # Scan all users
    uv run python scripts/trigger_scan.py --all
"""

import argparse
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from src.db.schema import init_db
from src.pipeline.scan_and_notify import scan_user, scan_all_users


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--user-id")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    init_db()

    if args.all:
        results = scan_all_users()
        for uid, ids in results.items():
            print(f"{uid}: created {len(ids)} proposals")
    else:
        ids = scan_user(args.user_id)
        print(f"Created {len(ids)} proposals for {args.user_id}: {ids}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add scripts/trigger_scan.py && git commit -m "feat(scripts): add manual scan trigger for demo"
```

---

## Task 16: End-to-End Smoke Test

**Files:** no new files

- [ ] **Step 1: Ensure all prerequisites are done**

Verify:
- `backend/.env` has `TELEGRAM_BOT_TOKEN`, `DUFFEL_API_KEY`, `LITEAPI_PRIVATE_KEY`, `ZENMUX_API_KEY`, `TAVILY_API_KEY`
- `backend/google_client_secret.json` exists
- You have messaged your Telegram bot at least once (so bot can push to you)
- Your Google Calendar has events + at least one 5+ day gap in the next 60 days

- [ ] **Step 2: Run the full pipeline**

```bash
cd /Users/jamie/Documents/nomie-hackathon && \
  uv --project backend run python scripts/google_oauth_setup.py --user-id <your_telegram_user_id> && \
  uv --project backend run python scripts/seed_demo_user.py --user-id <your_telegram_user_id> && \
  uv --project backend run python scripts/trigger_scan.py --user-id <your_telegram_user_id>
```

Expected timeline:
- OAuth setup: browser opens, you authorize, script prints success (~20 sec)
- Seed: prints user details (~1 sec)
- Trigger scan:
  - Logs: `Fetched N events`
  - Logs: `Found M qualifying free slots`
  - For each slot: `Generating bundle for slot...` (30–90 sec of LLM + tool calls)
  - Logs: `Inserted proposal <uuid>`
  - Logs: `Pushed Telegram notification for <uuid>`
- **Telegram notification arrives on your phone**

- [ ] **Step 3: Verify proposal in DB**

```bash
cd backend && uv run python -c "
from src.db import dao
users = dao.list_all_users()
for u in users:
    print(u['telegram_user_id'])
from src.db.connection import get_connection
conn = get_connection()
rows = conn.execute('SELECT proposal_id, slot_start_date, slot_end_date, status FROM proposals').fetchall()
for r in rows:
    print(dict(r))
"
```
Expected: Prints seeded user + at least one proposal row in `pending` status.

- [ ] **Step 4: Commit (nothing new; this is a checkpoint)**

No commit needed — this task is a verification gate.

---

## Stretch Task 17: Price Tracking for Confirmed Proposals

**Only do this if Tasks 1–16 are done and you have time.**

**Files:**
- Modify: `backend/src/pipeline/scan_and_notify.py`
- Create: `backend/src/pipeline/price_tracker.py`

- [ ] **Step 1: Create `price_tracker.py`**

```python
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
```

**Note:** Full price tracking requires storing IATA codes in `bundle_data.destinations[].iata` when proposals are generated. If time permits, go back and add that field in Task 12's prompt template. Otherwise, price tracking is documented as future work.

- [ ] **Step 2: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/pipeline/price_tracker.py && git commit -m "feat(pipeline): add price tracker skeleton (stretch)"
```

---

## Stretch Task 18: Confirm Endpoint (Writes Calendar Event)

**Only do this if Web teammate is ready to call it.**

**Files:**
- Create: `backend/src/pipeline/confirm_handler.py`

- [ ] **Step 1: Create `confirm_handler.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
cd /Users/jamie/Documents/nomie-hackathon && git add backend/src/pipeline/confirm_handler.py && git commit -m "feat(pipeline): add confirm/reject handlers with calendar write (stretch)"
```

---

## Self-Review Notes (for the executor)

After finishing Tasks 1–16, verify:

1. **Spec coverage check:**
   - §3 data model → Task 2 ✓
   - §4 onboarding (OAuth via local script) → Task 4 ✓
   - §5 scan logic → Task 13 ✓
   - §7 notification rules ① (new proposal) → Task 13 ✓
   - §7 notification rules ⑤ (price drop) → stretch Task 17
   - §8 telegram minimal format → Task 11 ✓
   - §9 calendar integration → Tasks 5, 6 ✓
   - §10 price tracking → stretch Task 17
   - Appendix B tool bindings → Tasks 7, 8, 9, 10 ✓

2. **Core demo path works end-to-end** (Task 16 passes): OAuth → seed → trigger → Telegram arrives → DB has proposal row.

3. **Known gaps (acceptable for hackathon):**
   - No real Web frontend link (using `PROPOSAL_URL_BASE` placeholder)
   - No price tracking (stretch)
   - No confirm flow integrated with Web (stretch)
   - LiteAPI may fail if endpoint shape differs — web_search fallback will kick in

---

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

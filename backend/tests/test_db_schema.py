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

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

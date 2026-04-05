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

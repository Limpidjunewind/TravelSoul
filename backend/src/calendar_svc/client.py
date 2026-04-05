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

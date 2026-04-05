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

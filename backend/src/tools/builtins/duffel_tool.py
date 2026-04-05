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

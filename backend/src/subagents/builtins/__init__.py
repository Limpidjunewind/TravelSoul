"""Built-in subagent configurations for Nomie travel planning."""

from .flight_search import FLIGHT_SEARCH_CONFIG
from .hotel_search import HOTEL_SEARCH_CONFIG
from .itinerary_planner import ITINERARY_PLANNER_CONFIG
from .travel_tips import TRAVEL_TIPS_CONFIG

__all__ = [
    "FLIGHT_SEARCH_CONFIG",
    "HOTEL_SEARCH_CONFIG",
    "ITINERARY_PLANNER_CONFIG",
    "TRAVEL_TIPS_CONFIG",
]

# Registry of built-in subagents
BUILTIN_SUBAGENTS = {
    "flight-search": FLIGHT_SEARCH_CONFIG,
    "hotel-search": HOTEL_SEARCH_CONFIG,
    "itinerary-planner": ITINERARY_PLANNER_CONFIG,
    "travel-tips": TRAVEL_TIPS_CONFIG,
}

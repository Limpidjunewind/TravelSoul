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
    agent = make_lead_agent({})
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

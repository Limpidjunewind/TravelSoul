"""Invoke the Nomie Lead Agent programmatically for pipeline use."""

import asyncio
import json
import logging
import uuid

from langchain_core.messages import HumanMessage

from src.agents.lead_agent import make_lead_agent

logger = logging.getLogger(__name__)


PIPELINE_PROMPT_TEMPLATE = """You are Nomie running in AUTONOMOUS PROACTIVE mode. The user is NOT available to answer questions. You MUST NOT ask any clarifying questions. Make reasonable assumptions and proceed.

USER PROFILE:
- Origin city: {origin_city} (IATA: SIN)
- Interested destinations: {destinations}
- Preferences: {vague_preferences}
- Budget per person: {budget} SGD
- Travelers: {travelers}

CONFIRMED TRAVEL DATES (already fixed, do not question):
- Departure: {slot_start}
- Return: {slot_end}
- Duration: {days} days

DESTINATIONS TO PLAN (already picked for the user — do NOT ask which to pick):
- Option 1: Tokyo, Japan (airport code NRT)
- Option 2: Jeju Island, South Korea (airport code CJU)

YOUR TASK (execute directly, no clarification):
1. For Tokyo: call flight-search sub-agent ONCE (origin=SIN, dest=NRT, depart={slot_start}, return={slot_end}). Then call hotel-search sub-agent ONCE for Tokyo with the same dates.
2. For Jeju: call flight-search sub-agent ONCE (origin=SIN, dest=CJU, depart={slot_start}, return={slot_end}). Then call hotel-search sub-agent ONCE for Jeju.
3. Add a brief 3-day itinerary and 2-3 tips for each.
4. Output the final JSON.

STRICT RULES:
- NEVER ask "which destination" — Tokyo and Jeju are already chosen.
- NEVER ask about dates — they are already fixed.
- Do NOT call the same sub-agent more than twice for the same destination.
- If a sub-agent fails or returns nothing, put an empty array [] in that field and move on.

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
    thread_id = f"pipeline-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}
    agent = make_lead_agent(config)
    state = {"messages": [HumanMessage(content=prompt)]}
    result = await agent.ainvoke(state, config=config, context={"thread_id": thread_id})
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

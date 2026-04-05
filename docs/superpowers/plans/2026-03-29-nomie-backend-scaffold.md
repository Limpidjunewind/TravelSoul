# Nomie Backend Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Copy DeerFlow backend to `backend/`, strip unused middleware, replace 2 generic sub-agents with 4 travel-specific sub-agent stubs, and verify it boots.

**Architecture:** DeerFlow backend copied as-is, then surgically modified: Lead Agent loses SandboxMiddleware and TodoMiddleware, gains hardcoded `subagent_enabled=True` and `max_concurrent=4`. The 2 generic sub-agents (general-purpose, bash) are replaced by 4 travel-specific sub-agents with placeholder prompts. Thread pool expanded from 3 to 4 workers.

**Tech Stack:** Python, LangGraph, LangChain

---

## File Structure

**Copy (entire directory):**
- `deer-flow/backend/` → `backend/`

**Modify:**
- `backend/src/agents/lead_agent/agent.py` — remove SandboxMiddleware, TodoMiddleware, hardcode subagent settings
- `backend/src/agents/lead_agent/prompt.py` — update `_build_subagent_section()` to list 4 travel sub-agents
- `backend/src/subagents/builtins/__init__.py` — replace registry with 4 travel types
- `backend/src/tools/builtins/task_tool.py` — update `Literal` type and error message
- `backend/src/subagents/executor.py` — change thread pool to 4 workers, `MAX_CONCURRENT_SUBAGENTS` to 4
- `backend/src/agents/middlewares/subagent_limit_middleware.py` — raise `MAX_SUBAGENT_LIMIT` to allow 4

**Create:**
- `backend/src/subagents/builtins/flight_search.py`
- `backend/src/subagents/builtins/hotel_search.py`
- `backend/src/subagents/builtins/itinerary_planner.py`
- `backend/src/subagents/builtins/travel_tips.py`

**Delete:**
- `backend/src/subagents/builtins/general_purpose.py`
- `backend/src/subagents/builtins/bash_agent.py`

---

### Task 1: Copy DeerFlow backend

**Files:**
- Create: `backend/` (entire directory tree copied from `deer-flow/backend/`)

- [ ] **Step 1: Copy the backend directory**

```bash
cp -r "deer-flow/backend" "backend"
```

- [ ] **Step 2: Verify the copy**

```bash
ls backend/src/agents/lead_agent/
```

Expected: `__init__.py  agent.py  prompt.py`

- [ ] **Step 3: Commit**

```bash
git add backend/
git commit -m "chore: copy DeerFlow backend as development base"
```

---

### Task 2: Remove SandboxMiddleware and TodoMiddleware from Lead Agent

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py`

- [ ] **Step 1: Remove SandboxMiddleware from imports and middleware chain**

In `backend/src/agents/lead_agent/agent.py`, remove the import:

```python
from src.sandbox.middleware import SandboxMiddleware
```

And in `_build_middlewares()`, change line 218 from:

```python
middlewares = [ThreadDataMiddleware(), UploadsMiddleware(), SandboxMiddleware(), DanglingToolCallMiddleware()]
```

to:

```python
middlewares = [ThreadDataMiddleware(), UploadsMiddleware(), DanglingToolCallMiddleware()]
```

- [ ] **Step 2: Remove TodoMiddleware import and related code**

Remove the import:

```python
from src.agents.middlewares.todo_middleware import TodoMiddleware
```

Remove the entire `_create_todo_list_middleware()` function (lines 84-196).

In `_build_middlewares()`, remove these lines:

```python
is_plan_mode = config.get("configurable", {}).get("is_plan_mode", False)
todo_list_middleware = _create_todo_list_middleware(is_plan_mode)
if todo_list_middleware is not None:
    middlewares.append(todo_list_middleware)
```

- [ ] **Step 3: Hardcode subagent settings in `make_lead_agent()`**

In `make_lead_agent()`, replace these lines:

```python
is_plan_mode = cfg.get("is_plan_mode", False)
subagent_enabled = cfg.get("subagent_enabled", False)
max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)
```

with:

```python
subagent_enabled = True
max_concurrent_subagents = 4
```

Remove the `is_plan_mode` variable usage from `config["metadata"].update(...)` block (remove the `"is_plan_mode": is_plan_mode,` line).

- [ ] **Step 4: Remove bootstrap agent path**

In `make_lead_agent()`, remove the entire `if is_bootstrap:` block (lines 313-323) and the `is_bootstrap = cfg.get("is_bootstrap", False)` line.

- [ ] **Step 5: Verify the file parses**

```bash
cd backend && python -c "import ast; ast.parse(open('src/agents/lead_agent/agent.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/lead_agent/agent.py
git commit -m "refactor: remove SandboxMiddleware, TodoMiddleware, hardcode subagent settings"
```

---

### Task 3: Create 4 travel sub-agent configs with placeholder prompts

**Files:**
- Create: `backend/src/subagents/builtins/flight_search.py`
- Create: `backend/src/subagents/builtins/hotel_search.py`
- Create: `backend/src/subagents/builtins/itinerary_planner.py`
- Create: `backend/src/subagents/builtins/travel_tips.py`
- Delete: `backend/src/subagents/builtins/general_purpose.py`
- Delete: `backend/src/subagents/builtins/bash_agent.py`

- [ ] **Step 1: Create flight_search.py**

```python
"""Flight search sub-agent configuration."""

from src.subagents.config import SubagentConfig

FLIGHT_SEARCH_CONFIG = SubagentConfig(
    name="flight-search",
    description="Search and compare flights across multiple platforms. Use when the user wants to find flights for their trip.",
    system_prompt="""You are a flight search specialist. Your job is to search for flights based on the user's requirements and return the best options.

<guidelines>
- Search for flights matching the given origin, destination, dates, and passenger count
- Compare prices across available sources
- Return results sorted by price (lowest first)
- Include airline, flight number, route, departure/arrival times, and price
- Include booking links when available
- If a search source fails, note it and continue with other sources
</guidelines>

<output_format>
For each flight option, provide:
- Airline and flight number
- Route (origin → destination)
- Date and time
- Price (including taxes)
- Booking link (if available)
- Source where this was found

Return up to 5 options, sorted by price.
</output_format>
""",
    tools=None,
    disallowed_tools=["task", "ask_clarification", "present_files", "view_image"],
    model="inherit",
    max_turns=30,
    timeout_seconds=300,
)
```

- [ ] **Step 2: Create hotel_search.py**

```python
"""Hotel search sub-agent configuration."""

from src.subagents.config import SubagentConfig

HOTEL_SEARCH_CONFIG = SubagentConfig(
    name="hotel-search",
    description="Search and compare hotels and accommodations. Use when the user wants to find places to stay.",
    system_prompt="""You are a hotel search specialist. Your job is to search for accommodations based on the user's requirements and return the best options.

<guidelines>
- Search for hotels matching the given destination, dates, guest count, and budget
- Consider location convenience (proximity to attractions, transit)
- Compare prices and ratings across available sources
- Include hotel name, location, price per night, and rating
- Include booking links when available
</guidelines>

<output_format>
For each hotel option, provide:
- Hotel name
- Location (area, distance to key landmarks or transit)
- Price per night
- Rating (if available)
- Booking link (if available)
- Source where this was found

Return up to 5 options, sorted by value (considering price and rating).
</output_format>
""",
    tools=None,
    disallowed_tools=["task", "ask_clarification", "present_files", "view_image"],
    model="inherit",
    max_turns=30,
    timeout_seconds=300,
)
```

- [ ] **Step 3: Create itinerary_planner.py**

```python
"""Itinerary planner sub-agent configuration."""

from src.subagents.config import SubagentConfig

ITINERARY_PLANNER_CONFIG = SubagentConfig(
    name="itinerary-planner",
    description="Generate a day-by-day travel itinerary. Use when the user needs a trip schedule planned out.",
    system_prompt="""You are a travel itinerary planner. Your job is to create a practical day-by-day itinerary based on the user's destination, travel duration, and preferences.

<guidelines>
- Create a realistic daily schedule considering travel time between locations
- Prioritize attractions and activities the user mentioned
- Balance busy and relaxed days
- Consider opening hours and seasonal factors
- Group nearby attractions on the same day
</guidelines>

<output_format>
For each day, provide:
- Day number
- List of planned activities/attractions with approximate timing
- Brief notes on logistics (transport between spots, meal suggestions)

Keep the itinerary practical and not overpacked.
</output_format>
""",
    tools=None,
    disallowed_tools=["task", "ask_clarification", "present_files", "view_image"],
    model="inherit",
    max_turns=20,
    timeout_seconds=300,
)
```

- [ ] **Step 4: Create travel_tips.py**

```python
"""Travel tips sub-agent configuration."""

from src.subagents.config import SubagentConfig

TRAVEL_TIPS_CONFIG = SubagentConfig(
    name="travel-tips",
    description="Provide practical travel tips and warnings. Use when the user needs destination-specific advice.",
    system_prompt="""You are a travel tips specialist. Your job is to provide practical, up-to-date travel advice for the user's destination.

<guidelines>
- Cover visa requirements for the traveler's nationality
- Check weather conditions for the travel dates
- Recommend transportation options (airport to city, within city)
- Note currency, payment methods, and tipping customs
- Include safety tips and cultural considerations
- Mention connectivity (SIM cards, WiFi availability)
</guidelines>

<output_format>
Organize tips into clear categories:
- Visa & Entry Requirements
- Weather & Packing
- Transportation
- Currency & Payment
- Connectivity
- Other Tips

Keep each tip concise and actionable.
</output_format>
""",
    tools=None,
    disallowed_tools=["task", "ask_clarification", "present_files", "view_image"],
    model="inherit",
    max_turns=20,
    timeout_seconds=300,
)
```

- [ ] **Step 5: Delete old sub-agent configs**

```bash
rm backend/src/subagents/builtins/general_purpose.py
rm backend/src/subagents/builtins/bash_agent.py
```

- [ ] **Step 6: Verify all 4 files parse**

```bash
cd backend && python -c "
import ast
for f in ['src/subagents/builtins/flight_search.py', 'src/subagents/builtins/hotel_search.py', 'src/subagents/builtins/itinerary_planner.py', 'src/subagents/builtins/travel_tips.py']:
    ast.parse(open(f).read())
    print(f'{f}: OK')
"
```

Expected:
```
src/subagents/builtins/flight_search.py: OK
src/subagents/builtins/hotel_search.py: OK
src/subagents/builtins/itinerary_planner.py: OK
src/subagents/builtins/travel_tips.py: OK
```

- [ ] **Step 7: Commit**

```bash
git add backend/src/subagents/builtins/
git commit -m "feat: replace generic sub-agents with 4 travel-specific sub-agents"
```

---

### Task 4: Update sub-agent registry

**Files:**
- Modify: `backend/src/subagents/builtins/__init__.py`

- [ ] **Step 1: Replace registry contents**

Replace the entire file content with:

```python
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
```

- [ ] **Step 2: Verify import works**

```bash
cd backend && python -c "from src.subagents.builtins import BUILTIN_SUBAGENTS; print(list(BUILTIN_SUBAGENTS.keys()))"
```

Expected: `['flight-search', 'hotel-search', 'itinerary-planner', 'travel-tips']`

- [ ] **Step 3: Commit**

```bash
git add backend/src/subagents/builtins/__init__.py
git commit -m "refactor: update sub-agent registry to 4 travel types"
```

---

### Task 5: Update task_tool Literal type

**Files:**
- Modify: `backend/src/tools/builtins/task_tool.py`

- [ ] **Step 1: Update the subagent_type parameter**

In `backend/src/tools/builtins/task_tool.py`, change the function signature from:

```python
subagent_type: Literal["general-purpose", "bash"],
```

to:

```python
subagent_type: Literal["flight-search", "hotel-search", "itinerary-planner", "travel-tips"],
```

- [ ] **Step 2: Update the docstring**

Replace the "Available subagent types" section in the docstring:

```python
    """Delegate a task to a specialized subagent that runs in its own context.

    Available subagent types:
    - **flight-search**: Search and compare flights across multiple platforms.
    - **hotel-search**: Search and compare hotels and accommodations.
    - **itinerary-planner**: Generate a day-by-day travel itinerary.
    - **travel-tips**: Provide practical travel tips and warnings.

    Args:
        description: A short (3-5 word) description of the task for logging/display. ALWAYS PROVIDE THIS PARAMETER FIRST.
        prompt: The task description for the subagent. Be specific about destination, dates, budget, and preferences. ALWAYS PROVIDE THIS PARAMETER SECOND.
        subagent_type: The type of subagent to use. ALWAYS PROVIDE THIS PARAMETER THIRD.
        max_turns: Optional maximum number of agent turns. Defaults to subagent's configured max.
    """
```

- [ ] **Step 3: Update the error message**

Change the error message from:

```python
return f"Error: Unknown subagent type '{subagent_type}'. Available: general-purpose, bash"
```

to:

```python
return f"Error: Unknown subagent type '{subagent_type}'. Available: flight-search, hotel-search, itinerary-planner, travel-tips"
```

- [ ] **Step 4: Verify the file parses**

```bash
cd backend && python -c "import ast; ast.parse(open('src/tools/builtins/task_tool.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/src/tools/builtins/task_tool.py
git commit -m "refactor: update task_tool to use 4 travel sub-agent types"
```

---

### Task 6: Expand thread pool and concurrency limit to 4

**Files:**
- Modify: `backend/src/subagents/executor.py`
- Modify: `backend/src/agents/middlewares/subagent_limit_middleware.py`

- [ ] **Step 1: Update executor thread pools and constant**

In `backend/src/subagents/executor.py`, change:

```python
_scheduler_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-scheduler-")
```
to:
```python
_scheduler_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="subagent-scheduler-")
```

Change:
```python
_execution_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-exec-")
```
to:
```python
_execution_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="subagent-exec-")
```

Change:
```python
MAX_CONCURRENT_SUBAGENTS = 3
```
to:
```python
MAX_CONCURRENT_SUBAGENTS = 4
```

- [ ] **Step 2: Update SubagentLimitMiddleware max range**

In `backend/src/agents/middlewares/subagent_limit_middleware.py`, change:

```python
MAX_SUBAGENT_LIMIT = 4
```

to:

```python
MAX_SUBAGENT_LIMIT = 5
```

This allows `_clamp_subagent_limit(4)` to return 4 (the current range is [2, 4], which already includes 4, but raising the upper bound to 5 gives us breathing room if we ever need 5).

Actually, check: `_clamp_subagent_limit(4)` with `MAX_SUBAGENT_LIMIT = 4` returns `min(4, 4) = 4`. This already works. **No change needed here.** Skip this sub-step.

- [ ] **Step 3: Verify constants**

```bash
cd backend && python -c "
from src.subagents.executor import MAX_CONCURRENT_SUBAGENTS
print(f'MAX_CONCURRENT_SUBAGENTS: {MAX_CONCURRENT_SUBAGENTS}')
"
```

Expected: `MAX_CONCURRENT_SUBAGENTS: 4`

- [ ] **Step 4: Commit**

```bash
git add backend/src/subagents/executor.py
git commit -m "refactor: expand thread pool and concurrency limit to 4 sub-agents"
```

---

### Task 7: Update Lead Agent subagent prompt section

**Files:**
- Modify: `backend/src/agents/lead_agent/prompt.py`

- [ ] **Step 1: Update `_build_subagent_section()` to list 4 travel sub-agents**

In `backend/src/agents/lead_agent/prompt.py`, replace the entire `_build_subagent_section()` function with:

```python
def _build_subagent_section(max_concurrent: int) -> str:
    """Build the subagent system prompt section for Nomie travel planning."""
    return f"""<subagent_system>
You have 4 specialized travel sub-agents. When the user confirms they want to start searching,
dispatch ALL 4 sub-agents in parallel using the `task` tool.

**Available Sub-agents:**
- **flight-search**: Search and compare flights across multiple platforms
- **hotel-search**: Search and compare hotels and accommodations
- **itinerary-planner**: Generate a day-by-day travel itinerary
- **travel-tips**: Provide practical travel tips and destination advice

**Dispatch Rules:**
- When the user says "start search", "go search", "开始搜索", or similar, dispatch all 4 sub-agents
- Each task() call must include ALL relevant travel details in the prompt (destination, dates, travelers, budget, preferences)
- Maximum {max_concurrent} task() calls per response
- After all sub-agents return, synthesize their results into a clear summary for the user

**Example dispatch:**
```python
task(description="Search flights", prompt="Search flights from Shanghai to Tokyo, Apr 30 - May 4, 2 passengers, budget under 3000 CNY per person", subagent_type="flight-search")
task(description="Search hotels", prompt="Search hotels in Tokyo Shinjuku area, check-in Apr 30 check-out May 4, 2 guests, budget under 500 CNY per night, prefer convenient transit access", subagent_type="hotel-search")
task(description="Plan itinerary", prompt="Create a 5-day Tokyo itinerary, interests: Senso-ji temple, Akihabara, Shibuya. Prefer mix of sightseeing and shopping", subagent_type="itinerary-planner")
task(description="Travel tips", prompt="Provide travel tips for Tokyo, Japan. Traveling from China, dates Apr 30 - May 4. Need visa, weather, transport, and payment info", subagent_type="travel-tips")
```
</subagent_system>"""
```

- [ ] **Step 2: Verify the file parses**

```bash
cd backend && python -c "import ast; ast.parse(open('src/agents/lead_agent/prompt.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/src/agents/lead_agent/prompt.py
git commit -m "refactor: update subagent prompt section for 4 travel sub-agents"
```

---

### Task 8: Create config.yaml and .env

**Files:**
- Create: `backend/config.yaml` (or project root `config.yaml`)
- Create: `backend/.env`

- [ ] **Step 1: Copy and modify config.yaml**

```bash
cp deer-flow/config.example.yaml backend/config.yaml
```

Then edit `backend/config.yaml` to keep only `web_search` and `web_fetch` tools, remove sandbox-related tools. The exact edits depend on the content of `config.example.yaml` — inspect it, then remove any sandbox/bash tool entries and keep only the web search/fetch entries.

- [ ] **Step 2: Create .env with API keys**

Create `backend/.env`:

```
OPENAI_API_KEY=your-openai-key-here
TAVILY_API_KEY=your-tavily-key-here
```

Make sure `.env` is in `.gitignore`.

- [ ] **Step 3: Verify .env is gitignored**

```bash
grep -q "\.env" .gitignore && echo "OK" || echo "MISSING"
```

Expected: `OK`

- [ ] **Step 4: Commit config.yaml only (not .env)**

```bash
git add backend/config.yaml
git commit -m "chore: add Nomie-specific config.yaml"
```

---

### Task 9: Boot test

- [ ] **Step 1: Install dependencies**

```bash
cd backend && uv install
```

Or if using pip:

```bash
cd backend && pip install -e .
```

- [ ] **Step 2: Start LangGraph server**

```bash
cd backend && make dev
```

Or:

```bash
cd backend && langgraph dev
```

- [ ] **Step 3: Verify server is running**

```bash
curl -s http://localhost:2024/ok | head -20
```

Expected: Some response indicating the server is up.

- [ ] **Step 4: If boot fails, read the error and fix**

Common issues:
- Missing API keys → check `.env`
- Import errors from deleted modules → check if any remaining code imports `general_purpose` or `bash_agent`
- Config issues → check `config.yaml` format

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve boot issues after scaffold setup"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-03-29-nomie-backend-scaffold.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

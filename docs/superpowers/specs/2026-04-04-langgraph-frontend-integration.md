# LangGraph Frontend Integration Design

## Goal

Replace all mock data in the frontend with real LangGraph Server API calls, enabling: streaming chat with Lead Agent, real-time sub-agent progress in AgentPanel, structured result display, session history from threads, and run cancellation.

## Scope

- Only LangGraph Server integration (port 2024)
- Gateway (auth + favorites) stays mocked — separate integration later
- No UI component redesign — existing components are reused as-is

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Session history | Include | Sidebar already built, TitleMiddleware ready, just swap data source |
| AgentPanel detail | Full steps | `task_running` events map naturally to steps array, minimal extra code |
| Result structuring | Lead Agent JSON | Follows DeerFlow pattern: sub-agents return text, Lead Agent summarizes |
| Chat streaming | Token-by-token | Standard UX, SSE `messages-tuple` events support this natively |
| Stop execution | Real cancel | LangGraph provides cancel API, frontend button already exists |

## Architecture

### New Files

```
frontend/src/
├── api/
│   └── langgraph.js          # Pure HTTP/SSE calls, no React
├── hooks/
│   └── useLanggraph.js       # React hook: SSE parsing + state management
```

### Modified Files

```
frontend/src/
├── pages/
│   └── MainPage.jsx           # Delete all MOCK_* data, wire to useLanggraph hook
├── components/
│   ├── Chat/Chat.jsx          # Support streaming message (text updates in-place)
│   ├── ResultPanel/ResultPanel.jsx  # Parse Lead Agent JSON output
│   └── Sidebar/Sidebar.jsx    # Minor: receives real session data (no code change needed)
```

### Unchanged Files

```
frontend/src/
├── components/
│   └── AgentPanel/AgentPanel.jsx   # Already supports { id, status, summary, steps } shape
├── pages/
│   └── LoginPage.jsx               # Gateway scope, not this integration
├── App.jsx                          # Gateway scope, not this integration
```

## Layer 1: API Module (`api/langgraph.js`)

Pure functions wrapping LangGraph Server HTTP calls. No React dependencies.

**Base URL**: `http://localhost:2024` (configurable via env var)

### Functions

| Function | HTTP Call | Returns |
|----------|----------|---------|
| `createThread()` | `POST /threads` | `{ thread_id }` |
| `getThreads()` | `GET /threads` | `[{ thread_id, metadata, created_at }]` |
| `getThreadState(threadId)` | `GET /threads/{id}/state` | `{ values: { messages, title } }` |
| `streamRun(threadId, message, onEvent)` | `POST /threads/{id}/runs/stream` | Returns `{ close }` handle for cleanup |
| `cancelRun(threadId, runId)` | `POST /threads/{id}/runs/{runId}/cancel` | `void` |

### `streamRun` Detail

Uses `fetch` with streaming response body (not `EventSource`, because we need POST with JSON body).

Request:
```json
{
  "input": {
    "messages": [{ "role": "user", "content": "user text" }]
  },
  "config": {
    "configurable": {
      "subagent_enabled": true
    }
  },
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

Parses SSE text stream line by line. Calls `onEvent(eventType, data)` for each parsed event.

Returns a handle with `close()` method to abort the fetch (used by stop button).

## Layer 2: React Hook (`hooks/useLanggraph.js`)

Custom hook that manages all LangGraph-related state and exposes a clean interface to MainPage.

### Interface

```js
const {
  // State
  messages,        // chat messages array
  agents,          // 4-agent status array for AgentPanel
  results,         // structured results for ResultPanel (null until ready)
  sessions,        // thread list for Sidebar
  currentThreadId, // active thread ID
  isSending,       // loading state for chat input

  // Actions
  sendMessage,     // (text) => void — send user message, handles streaming
  stopExecution,   // () => void — cancel current run
  newSession,      // () => void — create new thread
  selectSession,   // (threadId) => void — switch to existing thread
  loadSessions,    // () => void — refresh thread list
} = useLanggraph()
```

### SSE Event Handling

The hook registers an `onEvent` callback with `streamRun`:

**`messages-tuple` events** (Lead Agent text):
- AI text chunks → append to last message in `messages` array (streaming effect)
- AI tool calls to `task()` → extract `subagent_type` from arguments, map `tool_call_id` to agent ID
- This mapping is how we know which `task_id` corresponds to which agent card

**`custom` events** (sub-agent progress):
- `task_started` → set agent status to `working`, set summary from `description`
- `task_running` → append a step to the agent's steps array, extracted from `message` content
- `task_completed` → set agent status to `done`
- `task_failed` / `task_timed_out` → set agent status to `error`

**`values` events** (state snapshots):
- Extract `title` for session display
- After all 4 agents complete, the Lead Agent generates a final summary
- The final AI message contains the structured JSON result
- Parse it and set `results` state

### Task-to-Agent Mapping

Critical detail: how does the hook know that `task_id=abc123` belongs to the "flight" agent?

1. When Lead Agent calls `task()`, the `messages-tuple` event includes the tool call with `subagent_type` argument and `tool_call_id`
2. The hook builds a map: `{ [tool_call_id]: "flight-search" }`
3. When `task_started` arrives with `task_id` (which equals `tool_call_id`), look up the map
4. Map `subagent_type` to agent panel ID: `flight-search` → `flight`, `hotel-search` → `hotel`, etc.

### Phase Transitions

The hook doesn't manage phases directly — MainPage's state machine still controls that. But the hook signals phase-relevant events:

- `sendMessage` returns `{ shouldStartSearch: boolean }` — determined by whether Lead Agent calls `task()` tools
- When all 4 agents reach terminal status → MainPage transitions to `result` phase
- `stopExecution` → MainPage transitions back to `chat` phase

## Layer 3: MainPage Changes

### What Gets Deleted

- `MOCK_SESSIONS`, `MOCK_FAVORITES` (favorites stays mock but moves to Gateway scope later)
- `MOCK_AGENTS`, `MOCK_RESULTS`
- `buildExecutionStages()`, `buildIdleAgents()`, `patchAgent()`
- `requestAssistantReply()`
- `runExecutionTimeline()`, `executionTimersRef`, `clearExecutionTimers()`

### What Gets Simplified

MainPage becomes a thin orchestrator:

```js
function MainPage({ onLogout }) {
  const [phase, setPhase] = useState(PHASE.CHAT)
  const [favorites, setFavorites] = useState([])  // mock until Gateway
  const langgraph = useLanggraph()

  const handleChatSend = async (text) => {
    const { shouldStartSearch } = await langgraph.sendMessage(text)
    if (shouldStartSearch) {
      transitionPhase('START_EXECUTION')
    }
  }

  // ... phase transitions, favorites toggle, etc.
}
```

## Chat Streaming UX

### Message Shape Change

Current messages are `{ id, role, text }` where `text` is a complete string.

For streaming, add an `isStreaming` flag:

```js
{ id: 'msg-1', role: 'agent', text: 'Got it, let me', isStreaming: true }
// as tokens arrive, text grows:
{ id: 'msg-1', role: 'agent', text: 'Got it, let me search...', isStreaming: true }
// when complete:
{ id: 'msg-1', role: 'agent', text: 'Got it, let me search for flights and hotels!', isStreaming: false }
```

### Chat.jsx Change

Add a blinking cursor CSS class when `isStreaming` is true:

```jsx
<div className={`message-bubble ${msg.isStreaming ? 'streaming' : ''}`}>
  {msg.text}
</div>
```

## Result Parsing

Lead Agent's final message after all sub-agents complete will contain a JSON block. The prompt already instructs Lead Agent to summarize results.

We need to add a specific output format instruction to the Lead Agent's prompt for the summarization phase. The expected JSON shape:

```json
{
  "flights": [
    { "id": "f1", "airline": "...", "route": "...", "date": "...", "price": "...", "link": "..." }
  ],
  "hotels": [
    { "id": "h1", "name": "...", "location": "...", "price": "...", "rating": "...", "link": "..." }
  ],
  "itinerary": [
    { "day": 1, "plan": "..." }
  ],
  "tips": ["...", "..."]
}
```

The hook attempts `JSON.parse()` on the final AI message. If parsing fails (LLM output isn't perfect JSON), fall back to displaying the raw text as markdown.

## Step Text Extraction from `task_running`

The `message` field in `task_running` is a full AIMessage dict. To get a human-readable step:

1. If message has `tool_calls` → show tool name: "Searching Google Flights..." / "Fetching booking.com page..."
2. If message has text `content` → truncate to ~80 chars as summary
3. New steps are always `working` status; previous steps flip to `done`

## Error Handling

| Scenario | Behavior |
|----------|----------|
| SSE connection drops | Show error message in chat, transition to `chat` phase |
| Sub-agent fails/times out | Show error status on that agent card, other agents continue |
| All sub-agents fail | Show error message in chat, transition to `chat` phase |
| JSON parse fails on results | Fall back to rendering raw text as markdown |
| Network error on thread create | Show error message, stay on current state |

## Environment Configuration

Add to `frontend/.env` (or `.env.local`):

```
VITE_LANGGRAPH_URL=http://localhost:2024
```

Access in code: `import.meta.env.VITE_LANGGRAPH_URL`

## Not In Scope

- Gateway integration (auth, favorites) — separate design
- Pixel art sprites for agents — existing UI stays
- Mobile responsive — not a priority
- Offline/retry logic — keep simple for course project
- Lead Agent prompt changes for JSON output format — may need a small prompt addition, handled during implementation

# LangGraph Frontend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all mock data in the frontend with real LangGraph Server API calls — streaming chat, real-time agent progress, structured results, session history, and run cancellation.

**Architecture:** Two new files (`api/langgraph.js` for HTTP/SSE calls, `hooks/useLanggraph.js` for React state management) sit between the existing components and LangGraph Server. MainPage delegates all data fetching to the hook; the state machine (PHASE_TRANSITIONS) stays unchanged. SSE events drive chat streaming, agent panel updates, and result parsing.

**Tech Stack:** React 18, Vite, fetch API (ReadableStream for SSE), LangGraph Server REST API (port 2024)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `frontend/src/api/langgraph.js` | Pure HTTP/SSE functions — no React |
| Create | `frontend/src/hooks/useLanggraph.js` | React hook — SSE parsing, state, actions |
| Modify | `frontend/src/pages/MainPage.jsx` | Delete mocks, wire to hook |
| Modify | `frontend/src/components/Chat/Chat.jsx` | Streaming cursor CSS class |
| Modify | `frontend/src/components/Chat/Chat.css` | Blinking cursor animation |
| Modify | `frontend/src/components/ResultPanel/ResultPanel.jsx` | Markdown fallback when JSON parse fails |

---

### Task 1: Create API Module (`api/langgraph.js`)

**Files:**
- Create: `frontend/src/api/langgraph.js`

This module wraps all LangGraph Server HTTP calls. No React dependencies. Every function is a plain async function or returns a handle object.

- [ ] **Step 1: Create the API module with base URL config**

```js
// frontend/src/api/langgraph.js

const BASE_URL = import.meta.env.VITE_LANGGRAPH_URL || 'http://localhost:2024'

export async function createThread() {
  const res = await fetch(`${BASE_URL}/threads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ metadata: {} }),
  })
  if (!res.ok) throw new Error(`createThread failed: ${res.status}`)
  return res.json()
}

export async function searchThreads() {
  const res = await fetch(`${BASE_URL}/threads/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      limit: 50,
      offset: 0,
    }),
  })
  if (!res.ok) throw new Error(`searchThreads failed: ${res.status}`)
  return res.json()
}

export async function getThreadState(threadId) {
  const res = await fetch(`${BASE_URL}/threads/${threadId}/state`)
  if (!res.ok) throw new Error(`getThreadState failed: ${res.status}`)
  return res.json()
}

export async function cancelRun(threadId, runId) {
  const res = await fetch(`${BASE_URL}/threads/${threadId}/runs/${runId}/cancel`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`cancelRun failed: ${res.status}`)
}
```

- [ ] **Step 2: Add the `streamRun` function**

This is the core SSE function. It uses `fetch` with a streaming response body (not EventSource, because we need POST with JSON body). It parses the SSE text protocol line by line.

Add this to the same file, below `cancelRun`:

```js
export function streamRun(threadId, message, onEvent) {
  const abortController = new AbortController()

  const body = {
    input: {
      messages: [{ role: 'user', content: message }],
    },
    config: {
      configurable: {
        subagent_enabled: true,
      },
    },
    stream_mode: ['values', 'messages-tuple', 'custom'],
  }

  const promise = fetch(`${BASE_URL}/threads/${threadId}/runs/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: abortController.signal,
  }).then(async (res) => {
    if (!res.ok) {
      throw new Error(`streamRun failed: ${res.status}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const jsonStr = line.slice(6)
          try {
            const data = JSON.parse(jsonStr)
            onEvent(currentEvent, data)
          } catch {
            // skip malformed JSON lines
          }
        }
        // blank lines reset event type per SSE spec
        if (line === '') {
          currentEvent = ''
        }
      }
    }
  })

  return {
    promise,
    close: () => abortController.abort(),
    getAbortController: () => abortController,
  }
}
```

- [ ] **Step 3: Add the `.env` file for Vite**

Create `frontend/.env` (if it doesn't exist):

```
VITE_LANGGRAPH_URL=http://localhost:2024
```

- [ ] **Step 4: Verify the module loads without errors**

Run:
```bash
cd frontend && npx vite build --mode development 2>&1 | head -20
```

Expected: No import errors. The build may fail for other reasons (unused imports etc.) but `api/langgraph.js` should parse cleanly.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/langgraph.js frontend/.env
git commit -m "feat: add LangGraph API module with thread and streaming functions"
```

---

### Task 2: Create React Hook (`hooks/useLanggraph.js`)

**Files:**
- Create: `frontend/src/hooks/useLanggraph.js`

This hook manages all LangGraph state and exposes a clean interface. It handles SSE event parsing, task-to-agent mapping, streaming message assembly, and session management.

- [ ] **Step 1: Create the hook with state declarations and helper constants**

```js
// frontend/src/hooks/useLanggraph.js

import { useCallback, useRef, useState } from 'react'
import { createThread, searchThreads, getThreadState, streamRun, cancelRun } from '../api/langgraph.js'

const INITIAL_MESSAGES = [
  {
    id: 'welcome-1',
    role: 'agent',
    text: 'Hi there! Tell me about your trip — where to, when, and how many people?',
    isStreaming: false,
  },
]

const AGENT_TYPES = [
  { id: 'flight', name: 'Flight Search', icon: '✈️', sprite: '/assets/pixel/agent_1.png', subagentType: 'flight-search' },
  { id: 'hotel', name: 'Hotel Search', icon: '🏨', sprite: '/assets/pixel/agent_2.png', subagentType: 'hotel-search' },
  { id: 'itinerary', name: 'Itinerary Planner', icon: '📋', sprite: '/assets/pixel/agent_3.png', subagentType: 'itinerary-planner' },
  { id: 'tips', name: 'Travel Tips', icon: '🔍', sprite: '/assets/pixel/agent_4.png', subagentType: 'travel-tips' },
]

function buildIdleAgents() {
  return AGENT_TYPES.map((a) => ({
    ...a,
    status: 'idle',
    summary: 'Standby',
    steps: [],
  }))
}

// map subagent_type string to agent panel id
const SUBAGENT_TO_PANEL_ID = {
  'flight-search': 'flight',
  'hotel-search': 'hotel',
  'itinerary-planner': 'itinerary',
  'travel-tips': 'tips',
}

export function useLanggraph() {
  const [messages, setMessages] = useState(INITIAL_MESSAGES)
  const [agents, setAgents] = useState(buildIdleAgents)
  const [results, setResults] = useState(null)
  const [sessions, setSessions] = useState([])
  const [currentThreadId, setCurrentThreadId] = useState(null)
  const [isSending, setIsSending] = useState(false)

  // refs for values that change during streaming but shouldn't trigger re-renders
  const streamHandleRef = useRef(null)
  const currentRunIdRef = useRef(null)
  const taskMapRef = useRef({}) // tool_call_id -> panel agent id
```

- [ ] **Step 2: Add the `extractStepText` helper**

This function extracts a human-readable step label from an AIMessage dict inside a `task_running` event.

Add below the state declarations, inside the `useLanggraph` function:

```js
  // extract a short label from an AIMessage dict for the agent steps list
  function extractStepText(message) {
    // if the message has tool_calls, show the tool name
    if (message.tool_calls && message.tool_calls.length > 0) {
      const toolName = message.tool_calls[0].name
      const args = message.tool_calls[0].args || {}
      if (toolName === 'web_search') {
        const query = args.query || ''
        return query ? `Searching: ${query.slice(0, 60)}` : 'Searching the web...'
      }
      if (toolName === 'web_fetch') {
        const url = args.url || ''
        return url ? `Fetching: ${url.slice(0, 60)}` : 'Fetching a page...'
      }
      return `Using ${toolName}...`
    }
    // if the message has text content, truncate it
    const content = typeof message.content === 'string'
      ? message.content
      : Array.isArray(message.content)
        ? message.content.map((b) => (typeof b === 'string' ? b : b.text || '')).join('')
        : ''
    if (content) {
      return content.length > 80 ? content.slice(0, 77) + '...' : content
    }
    return 'Processing...'
  }
```

- [ ] **Step 3: Add the `handleSSEEvent` callback**

This is the core event handler called by `streamRun`. It processes three event types: `messages-tuple`, `custom`, and `values`.

Add below `extractStepText`:

```js
  // mutable flag set when Lead Agent calls task() — signals execution phase
  const didDispatchRef = useRef(false)

  function handleSSEEvent(eventType, data) {
    if (eventType === 'messages-tuple' || eventType === 'messages') {
      // messages-tuple carries individual message updates
      if (Array.isArray(data)) {
        // LangGraph sends [messageType, messageData] tuple format
        const [msgType, msgData] = data
        handleMessageTuple(msgType, msgData)
      } else if (data && data.type) {
        handleMessageTuple(data.type, data)
      }
    } else if (eventType === 'custom') {
      handleCustomEvent(data)
    } else if (eventType === 'values') {
      handleValuesEvent(data)
    }
  }

  function handleMessageTuple(msgType, msgData) {
    if (msgType === 'ai' || msgData.type === 'ai') {
      // check for tool calls to task() — this tells us execution is starting
      if (msgData.tool_calls && msgData.tool_calls.length > 0) {
        for (const tc of msgData.tool_calls) {
          if (tc.name === 'task') {
            didDispatchRef.current = true
            // build task_id -> panel agent id mapping
            const subagentType = tc.args?.subagent_type
            if (subagentType && tc.id) {
              taskMapRef.current[tc.id] = SUBAGENT_TO_PANEL_ID[subagentType] || subagentType
            }
          }
        }
        return // don't show tool call messages in chat
      }

      // AI text content — stream into chat
      const content = typeof msgData.content === 'string'
        ? msgData.content
        : Array.isArray(msgData.content)
          ? msgData.content.map((b) => (typeof b === 'string' ? b : b.text || '')).join('')
          : ''

      if (!content) return

      setMessages((prev) => {
        const last = prev[prev.length - 1]
        // if last message is a streaming agent message, append to it
        if (last && last.role === 'agent' && last.isStreaming) {
          return [
            ...prev.slice(0, -1),
            { ...last, text: last.text + content },
          ]
        }
        // otherwise start a new streaming message
        return [
          ...prev,
          { id: `msg-${Date.now()}`, role: 'agent', text: content, isStreaming: true },
        ]
      })
    }
    // tool result messages are ignored in the chat UI
  }

  function handleCustomEvent(data) {
    if (!data || !data.type) return
    const taskId = data.task_id
    const panelId = taskMapRef.current[taskId]
    if (!panelId) return

    if (data.type === 'task_started') {
      setAgents((prev) =>
        prev.map((a) =>
          a.id === panelId
            ? { ...a, status: 'working', summary: data.description || 'Starting...' }
            : a
        )
      )
    } else if (data.type === 'task_running') {
      const stepText = extractStepText(data.message || {})
      setAgents((prev) =>
        prev.map((a) => {
          if (a.id !== panelId) return a
          // flip previous working steps to done, add new working step
          const updatedSteps = a.steps.map((s) =>
            s.status === 'working' ? { ...s, status: 'done' } : s
          )
          return {
            ...a,
            summary: stepText,
            steps: [...updatedSteps, { text: stepText, status: 'working' }],
          }
        })
      )
    } else if (data.type === 'task_completed') {
      setAgents((prev) =>
        prev.map((a) =>
          a.id === panelId
            ? {
                ...a,
                status: 'done',
                summary: 'Completed',
                steps: a.steps.map((s) => ({ ...s, status: 'done' })),
              }
            : a
        )
      )
    } else if (data.type === 'task_failed' || data.type === 'task_timed_out') {
      setAgents((prev) =>
        prev.map((a) =>
          a.id === panelId
            ? { ...a, status: 'error', summary: data.error || 'Failed' }
            : a
        )
      )
    }
  }

  function handleValuesEvent(data) {
    // extract run_id for cancel support
    if (data.run_id) {
      currentRunIdRef.current = data.run_id
    }
  }
```

- [ ] **Step 4: Add the `tryParseResults` helper**

This function attempts to extract structured JSON from the Lead Agent's final message. It looks for a JSON code block or tries parsing the whole text.

Add below `handleValuesEvent`:

```js
  function tryParseResults(text) {
    // try to find a JSON code block first
    const jsonBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)```/)
    if (jsonBlockMatch) {
      try {
        return JSON.parse(jsonBlockMatch[1].trim())
      } catch {
        // fall through
      }
    }
    // try to find a raw JSON object
    const braceStart = text.indexOf('{')
    const braceEnd = text.lastIndexOf('}')
    if (braceStart !== -1 && braceEnd > braceStart) {
      try {
        return JSON.parse(text.slice(braceStart, braceEnd + 1))
      } catch {
        // fall through
      }
    }
    return null
  }
```

- [ ] **Step 5: Add the `sendMessage` action**

This is the main action called when user sends a chat message. It creates a thread if needed, starts the SSE stream, and returns whether execution was dispatched.

Add below `tryParseResults`:

```js
  const sendMessage = useCallback(async (text) => {
    setIsSending(true)
    didDispatchRef.current = false
    taskMapRef.current = {}

    // add user message to chat
    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: 'user', text, isStreaming: false },
    ])

    try {
      // create thread if this is the first message
      let threadId = currentThreadId
      if (!threadId) {
        const thread = await createThread()
        threadId = thread.thread_id
        setCurrentThreadId(threadId)
      }

      // start SSE stream
      const handle = streamRun(threadId, text, handleSSEEvent)
      streamHandleRef.current = handle

      // wait for stream to complete
      await handle.promise

      // finalize: mark last streaming message as complete
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.isStreaming) {
          return [...prev.slice(0, -1), { ...last, isStreaming: false }]
        }
        return prev
      })

      // if agents were dispatched, check if they all completed and try to parse results
      if (didDispatchRef.current) {
        // get final thread state for the Lead Agent's summary message
        const state = await getThreadState(threadId)
        const allMessages = state?.values?.messages || []
        // find the last AI message (Lead Agent's summary)
        const lastAi = [...allMessages].reverse().find((m) => m.type === 'ai')
        if (lastAi) {
          const content = typeof lastAi.content === 'string'
            ? lastAi.content
            : Array.isArray(lastAi.content)
              ? lastAi.content.map((b) => (typeof b === 'string' ? b : b.text || '')).join('')
              : ''
          const parsed = tryParseResults(content)
          if (parsed) {
            setResults(parsed)
          } else {
            // fallback: store raw text so ResultPanel can render it
            setResults({ rawText: content })
          }
        }
      }

      return { shouldStartSearch: didDispatchRef.current }
    } catch (err) {
      // if aborted by user (stop button), don't show error
      if (err.name === 'AbortError') {
        return { shouldStartSearch: false }
      }
      setMessages((prev) => [
        ...prev,
        { id: `err-${Date.now()}`, role: 'agent', text: 'Sorry, something went wrong. Please try again.', isStreaming: false },
      ])
      return { shouldStartSearch: false }
    } finally {
      setIsSending(false)
      streamHandleRef.current = null
    }
  }, [currentThreadId])
```

- [ ] **Step 6: Add `stopExecution`, `newSession`, `selectSession`, and `loadSessions` actions**

Add below `sendMessage`:

```js
  const stopExecution = useCallback(async () => {
    // abort the SSE fetch
    if (streamHandleRef.current) {
      streamHandleRef.current.close()
      streamHandleRef.current = null
    }
    // try to cancel the run on the server
    if (currentThreadId && currentRunIdRef.current) {
      try {
        await cancelRun(currentThreadId, currentRunIdRef.current)
      } catch {
        // best effort — server may have already finished
      }
      currentRunIdRef.current = null
    }
    setAgents(buildIdleAgents())
  }, [currentThreadId])

  const newSession = useCallback(() => {
    setCurrentThreadId(null)
    setMessages(INITIAL_MESSAGES)
    setAgents(buildIdleAgents())
    setResults(null)
    setIsSending(false)
    taskMapRef.current = {}
    didDispatchRef.current = false
    if (streamHandleRef.current) {
      streamHandleRef.current.close()
      streamHandleRef.current = null
    }
  }, [])

  const selectSession = useCallback(async (threadId) => {
    setCurrentThreadId(threadId)
    setResults(null)
    setAgents(buildIdleAgents())
    setIsSending(false)

    try {
      const state = await getThreadState(threadId)
      const rawMessages = state?.values?.messages || []
      const chatMessages = rawMessages
        .filter((m) => m.type === 'human' || m.type === 'ai')
        .map((m, i) => ({
          id: m.id || `hist-${i}`,
          role: m.type === 'human' ? 'user' : 'agent',
          text: typeof m.content === 'string'
            ? m.content
            : Array.isArray(m.content)
              ? m.content.map((b) => (typeof b === 'string' ? b : b.text || '')).join('')
              : String(m.content),
          isStreaming: false,
        }))
      setMessages(chatMessages.length > 0 ? chatMessages : INITIAL_MESSAGES)
    } catch {
      setMessages(INITIAL_MESSAGES)
    }
  }, [])

  const loadSessions = useCallback(async () => {
    try {
      const threads = await searchThreads()
      // threads is an array of thread objects
      const sessionList = threads
        .filter((t) => t.values && t.values.title)
        .map((t) => ({
          id: t.thread_id,
          title: t.values.title || 'Untitled',
          date: t.created_at ? t.created_at.split('T')[0] : '',
        }))
      setSessions(sessionList)
    } catch {
      setSessions([])
    }
  }, [])

  return {
    messages,
    agents,
    results,
    sessions,
    currentThreadId,
    isSending,
    sendMessage,
    stopExecution,
    newSession,
    selectSession,
    loadSessions,
  }
}
```

- [ ] **Step 7: Verify the hook file parses without errors**

Run:
```bash
cd frontend && npx vite build --mode development 2>&1 | head -20
```

Expected: No syntax errors in `hooks/useLanggraph.js`.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/hooks/useLanggraph.js
git commit -m "feat: add useLanggraph hook with SSE parsing and state management"
```

---

### Task 3: Update Chat.jsx for Streaming Cursor

**Files:**
- Modify: `frontend/src/components/Chat/Chat.jsx:31`
- Modify: `frontend/src/components/Chat/Chat.css` (append)

- [ ] **Step 1: Add streaming CSS class to message bubble**

In `frontend/src/components/Chat/Chat.jsx`, find the message bubble rendering (line 31):

```jsx
            <div className="message-bubble">{msg.text}</div>
```

Replace with:

```jsx
            <div className={`message-bubble ${msg.isStreaming ? 'streaming' : ''}`}>
              {msg.text}
            </div>
```

- [ ] **Step 2: Add the blinking cursor CSS**

Append to `frontend/src/components/Chat/Chat.css`:

```css
.message-bubble.streaming::after {
  content: '▌';
  animation: blink 0.6s step-end infinite;
  margin-left: 2px;
  color: var(--color-primary);
}

@keyframes blink {
  50% { opacity: 0; }
}
```

- [ ] **Step 3: Verify the component renders**

Run:
```bash
cd frontend && npm run dev
```

Open the browser, check that the chat page loads without errors. The streaming class won't be visible yet (no real SSE), but no runtime errors should appear.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Chat/Chat.jsx frontend/src/components/Chat/Chat.css
git commit -m "feat: add streaming cursor animation to chat messages"
```

---

### Task 4: Update ResultPanel for Markdown Fallback

**Files:**
- Modify: `frontend/src/components/ResultPanel/ResultPanel.jsx`

When JSON parsing fails, the hook sets `results` to `{ rawText: "..." }`. ResultPanel needs to handle this case.

- [ ] **Step 1: Add rawText fallback rendering**

In `frontend/src/components/ResultPanel/ResultPanel.jsx`, find the opening of the component function (line 5):

```jsx
function ResultPanel({ results, favorites, onToggleFavorite }) {
  // check if an item is already in favorites
  const isFavorited = (id) => favorites.some(f => f.id === id)

  return (
    <div className="result-panel">
      <div className="result-header">
        <h3>🎉 Search Complete!</h3>
        <p>Here are the recommended options for you</p>
      </div>
```

Replace the entire component with:

```jsx
function ResultPanel({ results, favorites, onToggleFavorite }) {
  const isFavorited = (id) => favorites.some(f => f.id === id)

  // fallback: if results is raw text (JSON parse failed), show as plain text
  if (results.rawText) {
    return (
      <div className="result-panel">
        <div className="result-header">
          <h3>🎉 Search Complete!</h3>
        </div>
        <section className="result-section">
          <div className="raw-result-text">{results.rawText}</div>
        </section>
      </div>
    )
  }

  return (
    <div className="result-panel">
      <div className="result-header">
        <h3>🎉 Search Complete!</h3>
        <p>Here are the recommended options for you</p>
      </div>

      {/* Flights */}
      {results.flights && results.flights.length > 0 && (
        <section className="result-section">
          <h4>✈️ Flights</h4>
          <div className="result-cards">
            {results.flights.map((flight, i) => (
              <div key={flight.id || `f-${i}`} className="result-card">
                <div className="card-main">
                  <div className="card-title">{flight.airline}</div>
                  <div className="card-detail">{flight.route}</div>
                  <div className="card-detail">{flight.date}</div>
                  <div className="card-price">{flight.price}</div>
                </div>
                <div className="card-actions">
                  {flight.link && (
                    <a href={flight.link} className="action-link" target="_blank" rel="noreferrer">
                      View →
                    </a>
                  )}
                  <button
                    className={`fav-btn ${isFavorited(flight.id) ? 'active' : ''}`}
                    onClick={() => onToggleFavorite({
                      id: flight.id || `f-${i}`,
                      type: 'flight',
                      title: flight.airline,
                      price: flight.price,
                    })}
                  >
                    {isFavorited(flight.id) ? '⭐' : '☆'} Save
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Hotels */}
      {results.hotels && results.hotels.length > 0 && (
        <section className="result-section">
          <h4>🏨 Hotels</h4>
          <div className="result-cards">
            {results.hotels.map((hotel, i) => (
              <div key={hotel.id || `h-${i}`} className="result-card">
                <div className="card-main">
                  <div className="card-title">{hotel.name}</div>
                  <div className="card-detail">{hotel.location}</div>
                  <div className="card-price">{hotel.price}</div>
                </div>
                <div className="card-actions">
                  {hotel.link && (
                    <a href={hotel.link} className="action-link" target="_blank" rel="noreferrer">
                      View →
                    </a>
                  )}
                  <button
                    className={`fav-btn ${isFavorited(hotel.id) ? 'active' : ''}`}
                    onClick={() => onToggleFavorite({
                      id: hotel.id || `h-${i}`,
                      type: 'hotel',
                      title: hotel.name,
                      price: hotel.price,
                    })}
                  >
                    {isFavorited(hotel.id) ? '⭐' : '☆'} Save
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Itinerary */}
      {results.itinerary && results.itinerary.length > 0 && (
        <section className="result-section">
          <h4>📋 Itinerary</h4>
          <div className="itinerary-list">
            {results.itinerary.map((item, i) => (
              <div key={item.day || i} className="itinerary-item">
                <span className="day-badge">Day {item.day}</span>
                <span className="day-plan">{item.plan}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tips */}
      {results.tips && results.tips.length > 0 && (
        <section className="result-section">
          <h4>⚠️ Travel Tips</h4>
          <ul className="tips-list">
            {results.tips.map((tip, i) => (
              <li key={i}>{tip}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ResultPanel/ResultPanel.jsx
git commit -m "feat: add raw text fallback to ResultPanel for non-JSON agent output"
```

---

### Task 5: Rewrite MainPage to Use the Hook

**Files:**
- Modify: `frontend/src/pages/MainPage.jsx`

This is the biggest change. We delete all mock data and mock functions, and wire everything to `useLanggraph()`.

- [ ] **Step 1: Rewrite MainPage.jsx**

Replace the entire contents of `frontend/src/pages/MainPage.jsx` with:

```jsx
import { useEffect, useState } from 'react'
import Sidebar from '../components/Sidebar/Sidebar.jsx'
import Chat from '../components/Chat/Chat.jsx'
import AgentPanel from '../components/AgentPanel/AgentPanel.jsx'
import ResultPanel from '../components/ResultPanel/ResultPanel.jsx'
import { useLanggraph } from '../hooks/useLanggraph.js'
import './MainPage.css'

const PHASE = {
  CHAT: 'chat',
  EXECUTING: 'executing',
  RESULT: 'result',
}

const PHASE_TRANSITIONS = {
  [PHASE.CHAT]: {
    START_EXECUTION: PHASE.EXECUTING,
  },
  [PHASE.EXECUTING]: {
    STOP_EXECUTION: PHASE.CHAT,
    EXECUTION_DONE: PHASE.RESULT,
    EXECUTION_ERROR: PHASE.CHAT,
  },
  [PHASE.RESULT]: {
    NEW_CHAT: PHASE.CHAT,
    START_EXECUTION: PHASE.EXECUTING,
  },
}

function getNextPhase(currentPhase, eventType) {
  return PHASE_TRANSITIONS[currentPhase]?.[eventType] || currentPhase
}

function MainPage({ onLogout }) {
  const [phase, setPhase] = useState(PHASE.CHAT)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  // favorites stays as local state until Gateway integration
  const [favorites, setFavorites] = useState([])

  const langgraph = useLanggraph()

  // load session history on mount
  useEffect(() => {
    langgraph.loadSessions()
  }, [])

  // watch agent statuses — when all are done, transition to result phase
  useEffect(() => {
    if (phase !== PHASE.EXECUTING) return
    const allDone = langgraph.agents.every(
      (a) => a.status === 'done' || a.status === 'error' || a.status === 'idle'
    )
    const anyWorked = langgraph.agents.some(
      (a) => a.status === 'done' || a.status === 'error'
    )
    if (allDone && anyWorked) {
      const anySuccess = langgraph.agents.some((a) => a.status === 'done')
      if (anySuccess && langgraph.results) {
        setPhase(getNextPhase(phase, 'EXECUTION_DONE'))
      } else if (!anySuccess) {
        setPhase(getNextPhase(phase, 'EXECUTION_ERROR'))
      }
    }
  }, [langgraph.agents, langgraph.results, phase])

  const transitionPhase = (eventType) => {
    setPhase((current) => getNextPhase(current, eventType))
  }

  const handleChatSend = async (text) => {
    const { shouldStartSearch } = await langgraph.sendMessage(text)
    if (shouldStartSearch) {
      transitionPhase('START_EXECUTION')
    }
  }

  const handleStopAgents = async () => {
    await langgraph.stopExecution()
    transitionPhase('STOP_EXECUTION')
  }

  const handleNewSession = () => {
    langgraph.newSession()
    transitionPhase('NEW_CHAT')
  }

  const handleSelectSession = async (sessionId) => {
    await langgraph.selectSession(sessionId)
    // determine phase from loaded messages — if results exist, show result
    // for now, just go to chat phase
    setPhase(PHASE.CHAT)
  }

  const handleSelectFavorite = (favoriteId) => {
    // placeholder until Gateway integration
    setPhase(PHASE.RESULT)
  }

  const handleToggleFavorite = (item) => {
    const exists = favorites.find((f) => f.id === item.id)
    if (exists) {
      setFavorites(favorites.filter((f) => f.id !== item.id))
    } else {
      setFavorites([...favorites, item])
    }
  }

  const isExecuting = phase === PHASE.EXECUTING
  const isResult = phase === PHASE.RESULT
  const showRightPanel = isExecuting || isResult

  return (
    <div className="app-layout">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        sessions={langgraph.sessions}
        favorites={favorites}
        currentSessionId={langgraph.currentThreadId}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        onSelectFavorite={handleSelectFavorite}
        onLogout={onLogout}
      />
      <div className="main-content">
        <div className={`chat-area ${showRightPanel ? 'compressed' : 'full'}`}>
          <Chat
            phase={phase}
            onStopAgents={handleStopAgents}
            compressed={showRightPanel}
            messages={langgraph.messages}
            isSending={langgraph.isSending}
            onSendMessage={handleChatSend}
          />
        </div>
        {showRightPanel && (
          <div className="right-panel">
            {isExecuting && <AgentPanel agents={langgraph.agents} />}
            {isResult && langgraph.results && (
              <ResultPanel
                results={langgraph.results}
                favorites={favorites}
                onToggleFavorite={handleToggleFavorite}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default MainPage
```

- [ ] **Step 2: Verify the app builds**

Run:
```bash
cd frontend && npx vite build --mode development 2>&1 | tail -10
```

Expected: Build succeeds without errors.

- [ ] **Step 3: Verify the app starts and renders**

Run:
```bash
cd frontend && npm run dev
```

Open the browser at `http://localhost:5173`. Verify:
- Login page shows (auth is still mocked)
- After "logging in", MainPage renders with empty Sidebar history and the welcome message
- Chat input is functional (typing, pressing Enter)
- No console errors

Note: Sending a message will fail if LangGraph Server is not running — that's expected. The UI should show the error fallback message "Sorry, something went wrong. Please try again."

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/MainPage.jsx
git commit -m "feat: replace all mock data with useLanggraph hook in MainPage"
```

---

### Task 6: End-to-End Smoke Test

**Files:**
- No file changes — this task is verification only

- [ ] **Step 1: Start the backend LangGraph Server**

```bash
cd backend && make dev
```

Wait for the server to start. Expected output includes `Application startup complete` on port 2024.

If it fails, check:
- `.env` file exists in `backend/` with `OPENAI_API_KEY` (or whichever LLM provider is configured)
- `config.yaml` exists and has valid model configuration
- Python dependencies are installed (`make install`)

- [ ] **Step 2: Start the frontend**

In a separate terminal:
```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Test the chat flow**

1. Open `http://localhost:5173`
2. Log in (mock login — just click Sign In)
3. Type "I want to go to Tokyo for 3 days from Shanghai, 2 people, budget 10000 RMB" and press Enter
4. Verify: the Lead Agent responds with clarifying questions or acknowledgment, text streams in character by character with a blinking cursor

- [ ] **Step 4: Test the execution flow**

1. After Lead Agent has enough info, type "start search" and press Enter
2. Verify:
   - Chat shows Lead Agent's response (streaming)
   - Phase transitions to `executing` — right panel appears with AgentPanel
   - Agent cards update from `idle` → `working` as `task_started` events arrive
   - Steps appear under each agent card as `task_running` events arrive
   - When all agents finish, phase transitions to `result` — ResultPanel shows
3. Check ResultPanel displays either structured cards (if JSON parsed) or raw text fallback

- [ ] **Step 5: Test the stop button**

1. Start a new session, trigger execution again
2. While agents are working, click "🛑 Stop Search"
3. Verify: agents reset to idle, phase goes back to chat

- [ ] **Step 6: Test session history**

1. After completing a search, click "New Trip" in sidebar
2. Verify: Sidebar shows the previous session with its auto-generated title
3. Click on the previous session
4. Verify: chat messages from that session are loaded

- [ ] **Step 7: Commit (if any fixes were needed)**

If any fixes were made during testing:
```bash
git add -A
git commit -m "fix: address issues found during end-to-end smoke test"
```

---

### Task 7: Update Lead Agent Prompt for JSON Output (if needed)

**Files:**
- Modify: `backend/src/agents/lead_agent/prompt.py`

This task is conditional — only needed if the Lead Agent's summary output is not parseable as JSON during Task 6 testing.

- [ ] **Step 1: Check if results parsed as JSON during Task 6**

If ResultPanel showed structured cards → skip this task.
If ResultPanel showed raw text fallback → continue.

- [ ] **Step 2: Add JSON output instruction to the subagent_system prompt section**

In `backend/src/agents/lead_agent/prompt.py`, find the `_build_subagent_section()` function. Add a result format instruction at the end of the section.

Find the return statement in `_build_subagent_section()` and add before the closing `</subagent_system>` tag:

```python
When all 4 sub-agents have completed, summarize their results into a single JSON code block. The JSON must follow this exact schema:

```json
{
  "flights": [{"id": "f1", "airline": "...", "route": "...", "date": "...", "price": "...", "link": "..."}],
  "hotels": [{"id": "h1", "name": "...", "location": "...", "price": "...", "rating": "...", "link": "..."}],
  "itinerary": [{"day": 1, "plan": "..."}],
  "tips": ["...", "..."]
}
```

Include the JSON block in your final message to the user. You may add a friendly introduction before the JSON block and a brief conclusion after it.
```

- [ ] **Step 3: Verify the prompt still parses**

```bash
cd backend && PYTHONPATH=. python -c "from src.agents.lead_agent.prompt import apply_prompt_template; print('OK')"
```

Expected: `OK` with no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/src/agents/lead_agent/prompt.py
git commit -m "feat: add JSON output format instruction to Lead Agent prompt"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Streaming chat (Task 2 handleMessageTuple, Task 3 cursor)
- [x] Agent panel with steps (Task 2 handleCustomEvent)
- [x] Structured results / markdown fallback (Task 2 tryParseResults, Task 4)
- [x] Session history (Task 2 loadSessions/selectSession, Task 5 Sidebar wiring)
- [x] Run cancellation (Task 2 stopExecution, Task 5 handleStopAgents)
- [x] Task-to-agent mapping (Task 2 SUBAGENT_TO_PANEL_ID + taskMapRef)
- [x] Error handling (Task 2 catch blocks, Task 4 rawText fallback)
- [x] Environment config (Task 1 Step 3)
- [x] Lead Agent JSON output prompt (Task 7)

**Placeholder scan:** No TBDs, TODOs, or vague steps found.

**Type consistency:**
- `messages` shape: `{ id, role, text, isStreaming }` — consistent across hook, MainPage, Chat.jsx
- `agents` shape: `{ id, name, icon, sprite, status, summary, steps }` — matches AgentPanel expectations
- `results` shape: `{ flights, hotels, itinerary, tips }` or `{ rawText }` — handled by ResultPanel
- `sessions` shape: `{ id, title, date }` — matches Sidebar expectations

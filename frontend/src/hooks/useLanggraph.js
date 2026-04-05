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
  const [executionStarted, setExecutionStarted] = useState(false)

  // refs for values that change during streaming but shouldn't trigger re-renders
  const streamHandleRef = useRef(null)
  const currentRunIdRef = useRef(null)
  const taskMapRef = useRef({}) // tool_call_id -> panel agent id

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

  // mutable flag set when Lead Agent calls task() — signals execution phase
  const didDispatchRef = useRef(false)

  function handleSSEEvent(eventType, data) {
    if (eventType === 'messages-tuple' || eventType === 'messages') {
      // LangGraph sends [messageChunk, metadata] array
      // messageChunk has .type, .content, .tool_calls etc.
      if (Array.isArray(data) && data.length >= 1) {
        const msgChunk = data[0]
        handleMessageChunk(msgChunk)
      } else if (data && data.type) {
        handleMessageChunk(data)
      }
    } else if (eventType === 'custom') {
      handleCustomEvent(data)
    } else if (eventType === 'values') {
      handleValuesEvent(data)
    } else if (eventType === 'metadata') {
      // extract run_id from metadata event
      if (data && data.run_id) {
        currentRunIdRef.current = data.run_id
      }
    }
  }

  function handleMessageChunk(msg) {
    // skip non-AI messages (human, tool results)
    const msgType = msg.type
    if (msgType !== 'AIMessageChunk' && msgType !== 'ai') return

    // skip tool call messages (task dispatch) — don't show in chat
    if (msg.tool_calls && msg.tool_calls.length > 0) return
    // skip tool_call_chunks (partial tool calls during streaming)
    if (msg.tool_call_chunks && msg.tool_call_chunks.length > 0) return

    // AI text content — stream into chat
    const content = typeof msg.content === 'string'
      ? msg.content
      : Array.isArray(msg.content)
        ? msg.content.map((b) => (typeof b === 'string' ? b : b.text || '')).join('')
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

  // infer panel agent id from task_started description
  function inferPanelId(description) {
    const desc = (description || '').toLowerCase()
    if (desc.includes('flight')) return 'flight'
    if (desc.includes('hotel') || desc.includes('accommodation')) return 'hotel'
    if (desc.includes('itinerary') || desc.includes('plan')) return 'itinerary'
    if (desc.includes('tip') || desc.includes('advice') || desc.includes('travel')) return 'tips'
    return null
  }

  function handleCustomEvent(data) {
    if (!data || !data.type) return
    const taskId = data.task_id

    // on task_started, build the task_id -> panel_id mapping from description
    if (data.type === 'task_started') {
      const panelId = inferPanelId(data.description)
      if (panelId) {
        taskMapRef.current[taskId] = panelId
      }
    }

    const panelId = taskMapRef.current[taskId]
    if (!panelId) return

    if (data.type === 'task_started') {
      didDispatchRef.current = true
      setExecutionStarted(true)
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

  function tryParseResults(text) {
    // 1. try JSON code block
    const jsonBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)```/)
    if (jsonBlockMatch) {
      try { return JSON.parse(jsonBlockMatch[1].trim()) } catch { /* fall through */ }
    }
    // 2. try raw JSON object
    const braceStart = text.indexOf('{')
    const braceEnd = text.lastIndexOf('}')
    if (braceStart !== -1 && braceEnd > braceStart) {
      try { return JSON.parse(text.slice(braceStart, braceEnd + 1)) } catch { /* fall through */ }
    }
    // 3. parse markdown structure from Lead Agent's natural language output
    return parseMarkdownResults(text)
  }

  function parseMarkdownResults(text) {
    const results = { flights: [], hotels: [], itinerary: [], tips: [] }

    // split by ### or ## headers
    const sections = text.split(/#{2,3}\s+/)

    for (const section of sections) {
      const lower = section.toLowerCase()
      if (lower.startsWith('航班') || lower.startsWith('flight')) {
        results.flights = parseFlights(section)
      } else if (lower.startsWith('酒店') || lower.startsWith('hotel') || lower.startsWith('accommodation')) {
        results.hotels = parseHotels(section)
      } else if (lower.startsWith('行程') || lower.startsWith('itinerary') || lower.startsWith('day')) {
        results.itinerary = parseItinerary(section)
      } else if (lower.startsWith('旅行') || lower.startsWith('travel') || lower.startsWith('tip') || lower.startsWith('注意')) {
        results.tips = parseTips(section)
      }
    }

    // if we found at least some data, return structured results
    const hasData = results.flights.length > 0 || results.hotels.length > 0 ||
                    results.itinerary.length > 0 || results.tips.length > 0
    return hasData ? results : null
  }

  function extractLink(text) {
    const match = text.match(/\[([^\]]*)\]\((https?:\/\/[^)]+)\)/)
    if (match) return match[2]
    const urlMatch = text.match(/(https?:\/\/[^\s)]+)/)
    return urlMatch ? urlMatch[1] : ''
  }

  function parseFlights(section) {
    // split by numbered items: "1." "2." etc.
    const items = section.split(/\n\s*\d+\.\s+/).filter(Boolean)
    return items.map((item, i) => {
      const lines = item.replace(/\n/g, ' ')
      // extract airline name from first bold text
      const airlineMatch = lines.match(/\*\*([^*]+)\*\*/)
      const airline = airlineMatch ? airlineMatch[1].replace(/航班\s*/, '') : `Flight ${i + 1}`
      // extract route
      const routeMatch = lines.match(/航线\*?\*?[:：]\s*([^-–\n]*(?:→|->|to)[^-–\n]*)/) ||
                         lines.match(/([A-Z]{3}\s*(?:→|->|to)\s*[A-Z]{3})/) ||
                         lines.match(/route\*?\*?[:：]\s*([^-–\n]*)/i)
      const route = routeMatch ? routeMatch[1].trim().replace(/\*\*/g, '') : ''
      // extract date
      const dateMatch = lines.match(/日期[^:：]*[:：]\s*([^-–]*?)(?=\s*-\s*\*|$)/) ||
                       lines.match(/date[^:：]*[:：]\s*([^-–]*?)(?=\s*-\s*\*|$)/i) ||
                       lines.match(/出发[^:：]*[:：]\s*([^-–]*?)(?=\s*-\s*\*|$)/)
      const date = dateMatch ? dateMatch[1].trim().replace(/\*\*/g, '').slice(0, 60) : ''
      // extract price
      const priceMatch = lines.match(/价格\*?\*?[:：]\s*([^-–\n]*?)(?=\s*-\s*\*|$)/) ||
                        lines.match(/price\*?\*?[:：]\s*([^-–\n]*?)(?=\s*-\s*\*|$)/i) ||
                        lines.match(/([\$¥€]\s*[\d,]+[^-–\n]*?)(?=\s*-\s*\*|$)/) ||
                        lines.match(/(\d+\s*(?:SGD|CNY|USD|RMB|新加坡元|人民币)[^-–\n]*?)(?=\s*-\s*\*|$)/)
      const price = priceMatch ? priceMatch[1].trim().replace(/\*\*/g, '') : ''
      const link = extractLink(lines)
      return { id: `f${i + 1}`, airline, route, date, price, link }
    }).filter((f) => f.airline !== `Flight 0`)
  }

  function parseHotels(section) {
    const items = section.split(/\n\s*\d+\.\s+/).filter(Boolean)
    return items.map((item, i) => {
      const lines = item.replace(/\n/g, ' ')
      const nameMatch = lines.match(/\*\*([^*]+)\*\*/)
      const name = nameMatch ? nameMatch[1] : `Hotel ${i + 1}`
      const locationMatch = lines.match(/位置\*?\*?[:：]\s*([^-–\n]*?)(?=\s*-\s*\*|$)/) ||
                           lines.match(/location\*?\*?[:：]\s*([^-–\n]*?)(?=\s*-\s*\*|$)/i)
      const location = locationMatch ? locationMatch[1].trim().replace(/\*\*/g, '') : ''
      const priceMatch = lines.match(/价格\*?\*?[:：]\s*([^-–\n]*?)(?=\s*-\s*\*|$)/) ||
                        lines.match(/price\*?\*?[:：]\s*([^-–\n]*?)(?=\s*-\s*\*|$)/i)
      const price = priceMatch ? priceMatch[1].trim().replace(/\*\*/g, '') : ''
      const ratingMatch = lines.match(/评[分级]\*?\*?[:：]\s*([^-–\n]*?)(?=\s*-\s*\*|$)/) ||
                         lines.match(/rating\*?\*?[:：]\s*([^-–\n]*?)(?=\s*-\s*\*|$)/i)
      const rating = ratingMatch ? ratingMatch[1].trim().replace(/\*\*/g, '') : ''
      const link = extractLink(lines)
      return { id: `h${i + 1}`, name, location, price, rating, link }
    }).filter((h) => h.name !== 'Hotel 0')
  }

  function parseItinerary(section) {
    const days = []
    // match patterns like "第1天" "Day 1" "**第1天**"
    const dayPattern = /(?:\*\*)?(?:第(\d+)天|Day\s*(\d+))(?:\*\*)?[:：]?\s*(.*?)(?=(?:\*\*)?(?:第\d+天|Day\s*\d+)|\s*$)/gi
    let match
    while ((match = dayPattern.exec(section)) !== null) {
      const dayNum = parseInt(match[1] || match[2])
      const plan = match[3].trim().replace(/\*\*/g, '').replace(/^[-–]\s*/, '')
      if (plan) days.push({ day: dayNum, plan })
    }
    // fallback: split by "- **第X天**" pattern
    if (days.length === 0) {
      const lines = section.split(/\n/).filter((l) => l.trim())
      let dayNum = 1
      for (const line of lines) {
        const cleaned = line.replace(/^[-\s*]+/, '').replace(/\*\*/g, '').trim()
        if (cleaned && cleaned.length > 5) {
          const numMatch = cleaned.match(/^第?(\d+)[天日]/)
          if (numMatch) dayNum = parseInt(numMatch[1])
          const plan = cleaned.replace(/^第?\d+[天日][：:]?\s*/, '')
          if (plan) days.push({ day: dayNum++, plan })
        }
      }
    }
    return days
  }

  function parseTips(section) {
    const tips = []
    const lines = section.split(/\n/)
    for (const line of lines) {
      const cleaned = line.replace(/^[-\s*]+/, '').replace(/\*\*/g, '').trim()
      if (cleaned && cleaned.length > 5 && !cleaned.match(/^#{2,}/)) {
        tips.push(cleaned)
      }
    }
    return tips
  }

  const sendMessage = useCallback(async (text) => {
    setIsSending(true)
    setExecutionStarted(false)
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

      // start SSE stream — DO NOT await, let events drive UI in real-time
      const handle = streamRun(threadId, text, handleSSEEvent)
      streamHandleRef.current = handle

      // handle stream completion in background
      handle.promise.then(async () => {
        // finalize: mark last streaming message as complete
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.isStreaming) {
            return [...prev.slice(0, -1), { ...last, isStreaming: false }]
          }
          return prev
        })

        // if agents were dispatched, parse results from final thread state
        if (didDispatchRef.current) {
          try {
            const state = await getThreadState(threadId)
            const allMessages = state?.values?.messages || []
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
                setResults({ rawText: content })
              }
            }
          } catch {
            // failed to get thread state, results stay null
          }
        }

        setIsSending(false)
        streamHandleRef.current = null
      }).catch((err) => {
        if (err.name !== 'AbortError') {
          setMessages((prev) => [
            ...prev,
            { id: `err-${Date.now()}`, role: 'agent', text: 'Sorry, something went wrong. Please try again.', isStreaming: false },
          ])
        }
        setIsSending(false)
        streamHandleRef.current = null
      })

    } catch (err) {
      // thread creation failed
      setMessages((prev) => [
        ...prev,
        { id: `err-${Date.now()}`, role: 'agent', text: 'Sorry, could not connect. Please try again.', isStreaming: false },
      ])
      setIsSending(false)
    }
  }, [currentThreadId])

  const stopExecution = useCallback(() => {
    // abort the SSE fetch
    if (streamHandleRef.current) {
      streamHandleRef.current.close()
      streamHandleRef.current = null
    }
    // reset execution state so useEffect doesn't re-trigger EXECUTING phase
    setExecutionStarted(false)
    setIsSending(false)
    didDispatchRef.current = false
    // try to cancel the run on the server (best effort, don't await)
    if (currentThreadId && currentRunIdRef.current) {
      cancelRun(currentThreadId, currentRunIdRef.current).catch(() => {})
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
    setExecutionStarted(false)
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
    executionStarted,
    sendMessage,
    stopExecution,
    newSession,
    selectSession,
    loadSessions,
  }
}

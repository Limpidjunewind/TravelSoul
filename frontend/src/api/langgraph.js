// frontend/src/api/langgraph.js

const BASE_URL = import.meta.env.VITE_LANGGRAPH_URL || 'http://localhost:2024'

// cache the assistant_id so we only fetch it once
let _assistantId = null

async function getAssistantId() {
  if (_assistantId) return _assistantId
  const res = await fetch(`${BASE_URL}/assistants/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graph_id: 'lead_agent' }),
  })
  if (!res.ok) throw new Error(`getAssistantId failed: ${res.status}`)
  const assistants = await res.json()
  if (!assistants.length) throw new Error('No lead_agent assistant found')
  _assistantId = assistants[0].assistant_id
  return _assistantId
}

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

export function streamRun(threadId, message, onEvent) {
  const abortController = new AbortController()

  const promise = getAssistantId().then(async (assistantId) => {
    const body = {
      assistant_id: assistantId,
      input: {
        messages: [{ role: 'user', content: message }],
      },
      config: {
        configurable: {
          thread_id: threadId,
          subagent_enabled: true,
        },
      },
      stream_mode: ['values', 'messages-tuple', 'custom'],
    }

    const res = await fetch(`${BASE_URL}/threads/${threadId}/runs/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: abortController.signal,
    })

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

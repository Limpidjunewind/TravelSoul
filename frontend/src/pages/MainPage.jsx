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

  // transition to executing as soon as first sub-agent starts
  useEffect(() => {
    if (langgraph.executionStarted && phase === PHASE.CHAT) {
      transitionPhase('START_EXECUTION')
    }
  }, [langgraph.executionStarted, phase])

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
    await langgraph.sendMessage(text)
    // phase transition is handled by executionStarted useEffect above
  }

  const handleStopAgents = () => {
    langgraph.stopExecution()
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

import { useState } from 'react'
import './AgentPanel.css'

// 2x2 grid of agent cards, shows what each agent is doing
// click on an agent to expand its step-by-step progress
function AgentPanel({ agents }) {
  const [expandedId, setExpandedId] = useState(null)

  const toggleExpand = (agentId) => {
    setExpandedId(expandedId === agentId ? null : agentId)
  }

  return (
    <div className="agent-panel">
      <div className="agent-panel-header">
        <h3>🎮 Agents Working...</h3>
      </div>
      <div className="agent-grid">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className={`agent-character ${agent.status}`}
            onClick={() => toggleExpand(agent.id)}
          >
            {agent.sprite ? (
              <img
                className={`agent-icon ${agent.status}`}
                src={agent.sprite}
                alt={agent.name}
              />
            ) : (
              <div className={`agent-icon ${agent.status}`}>
                {agent.icon}
              </div>
            )}
            <div className="agent-name">{agent.name}</div>
            <div className={`agent-status-badge ${agent.status}`}>
              {getStatusText(agent.status)}
            </div>
            <div className="agent-summary">{agent.summary}</div>

            {expandedId === agent.id && agent.steps.length > 0 && (
              <div className="agent-steps">
                {agent.steps.map((step, i) => (
                  <div key={i} className={`step ${step.status}`}>
                    <span className="step-icon">{getStepIcon(step.status)}</span>
                    <span className="step-text">{step.text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// map status key to display text
function getStatusText(status) {
  const map = { idle: 'Idle', working: 'Searching...', done: 'Done', error: 'Error' }
  return map[status] || status
}

// map step status to an emoji icon
function getStepIcon(status) {
  const map = { done: '✅', working: '🔄', pending: '⬜' }
  return map[status] || '⬜'
}

export default AgentPanel

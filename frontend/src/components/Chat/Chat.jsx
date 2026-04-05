import { useState } from 'react'
import './Chat.css'

// chat area where user talks to the agent
// message data and send flow are controlled by parent state machine
function Chat({ phase, onStopAgents, compressed, messages, isSending, onSendMessage }) {
  const [input, setInput] = useState('')

  // pass user input to parent; parent decides how state transitions happen
  const handleSend = async () => {
    const text = input.trim()
    if (!text || isSending) return

    setInput('')
    await onSendMessage(text)
  }

  // send on Enter; Shift+Enter keeps newline in textarea
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className={`chat-container ${compressed ? 'compressed' : ''}`}>
      <div className="chat-messages">
        {messages.map(msg => (
          <div key={msg.id} className={`message ${msg.role}`}>
            {msg.role === 'agent' && <span className="message-avatar">🤖</span>}
            <div className={`message-bubble ${msg.isStreaming ? 'streaming' : ''}`}>
              {msg.text}
            </div>
          </div>
        ))}
      </div>

      <div className="chat-input-area">
        {phase === 'executing' ? (
          <button className="stop-btn" onClick={onStopAgents}>
            🛑 Stop Search
          </button>
        ) : (
          <div className="input-row">
            <textarea
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={compressed ? 'Message...' : 'Describe your travel plans... (Enter to send)'}
              rows={1}
              disabled={isSending}
            />
            <button className="send-btn" onClick={handleSend} disabled={!input.trim() || isSending}>
              {isSending ? 'Sending...' : 'Send'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default Chat

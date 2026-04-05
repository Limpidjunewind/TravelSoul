import { useState } from 'react'
import './Sidebar.css'

// sidebar with favorites, session history, and sign out
// can be collapsed to save space
function Sidebar({
  collapsed,
  onToggle,
  sessions,
  favorites,
  currentSessionId,
  onNewSession,
  onSelectSession,
  onSelectFavorite,
  onLogout,
}) {
  const [favoritesOpen, setFavoritesOpen] = useState(true)
  const [historyOpen, setHistoryOpen] = useState(true)

  if (collapsed) {
    return (
      <div className="sidebar collapsed">
        <button className="sidebar-toggle" onClick={onToggle}>☰</button>
      </div>
    )
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-logo">✈️ Nomie</span>
        <button className="sidebar-toggle" onClick={onToggle}>✕</button>
      </div>

      <button className="new-session-btn" onClick={onNewSession}>
        <span>＋</span> New Trip
      </button>

      <div className="sidebar-sections">
        {/* Favorites */}
        <div className="sidebar-section">
          <button
            className="section-header"
            onClick={() => setFavoritesOpen(!favoritesOpen)}
          >
            <span>⭐ Favorites</span>
            <span className="section-arrow">{favoritesOpen ? '▾' : '▸'}</span>
          </button>
          {favoritesOpen && (
            <div className="section-list">
              {favorites.length === 0 && (
                <div className="section-empty">No favorites yet</div>
              )}
              {favorites.map(fav => (
                <button
                  key={fav.id}
                  className={`session-item ${currentSessionId === `fav-${fav.id}` ? 'active' : ''}`}
                  onClick={() => onSelectFavorite(fav.id)}
                >
                  <span>{fav.type === 'flight' ? '✈️' : '🏨'}</span>
                  <span className="item-title">{fav.title}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* History */}
        <div className="sidebar-section">
          <button
            className="section-header"
            onClick={() => setHistoryOpen(!historyOpen)}
          >
            <span>💬 History</span>
            <span className="section-arrow">{historyOpen ? '▾' : '▸'}</span>
          </button>
          {historyOpen && (
            <div className="section-list">
              {sessions.length === 0 && (
                <div className="section-empty">No history yet</div>
              )}
              {sessions.map(session => (
                <button
                  key={session.id}
                  className={`session-item ${currentSessionId === session.id ? 'active' : ''}`}
                  onClick={() => onSelectSession(session.id)}
                >
                  <span>📅</span>
                  <span className="item-title">{session.title}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="sidebar-footer">
        <button className="footer-btn" onClick={onLogout}>Sign Out</button>
      </div>
    </div>
  )
}

export default Sidebar

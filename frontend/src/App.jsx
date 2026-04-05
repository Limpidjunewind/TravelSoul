import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage.jsx'
import MainPage from './pages/MainPage.jsx'
import './App.css'

// top-level app component, handles auth routing
function App() {
  // TODO: Replace with real auth logic
  const [isLoggedIn, setIsLoggedIn] = useState(false)

  const handleLogin = () => setIsLoggedIn(true)

  const handleLogout = () => setIsLoggedIn(false)

  // redirect to /login if not logged in, otherwise show main page
  return (
    <Routes>
      <Route
        path="/login"
        element={
          isLoggedIn
            ? <Navigate to="/" replace />
            : <LoginPage onLogin={handleLogin} />
        }
      />
      <Route
        path="/*"
        element={
          isLoggedIn
            ? <MainPage onLogout={handleLogout} />
            : <Navigate to="/login" replace />
        }
      />
    </Routes>
  )
}

export default App

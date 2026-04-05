import { useState } from 'react'
import './LoginPage.css'

// login / register page with form validation
function LoginPage({ onLogin }) {
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [errors, setErrors] = useState({})

  // validate inputs before submit
  const validate = () => {
    const errs = {}
    if (!email.trim()) {
      errs.email = 'Email is required'
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      errs.email = 'Please enter a valid email'
    }
    if (!password) {
      errs.password = 'Password is required'
    } else if (password.length < 6) {
      errs.password = 'Password must be at least 6 characters'
    }
    if (isRegister && password !== confirmPw) {
      errs.confirmPw = 'Passwords do not match'
    }
    return errs
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const errs = validate()
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    // TODO: Real auth API call
    onLogin()
  }

  // clear errors when switching tabs
  const switchTab = (register) => {
    setIsRegister(register)
    setErrors({})
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <span className="logo-icon">✈️</span>
          <h1>Nomie</h1>
          <p className="login-subtitle">Your AI Travel Companion</p>
        </div>

        <div className="login-tabs">
          <button
            className={`login-tab ${!isRegister ? 'active' : ''}`}
            onClick={() => switchTab(false)}
          >
            Sign In
          </button>
          <button
            className={`login-tab ${isRegister ? 'active' : ''}`}
            onClick={() => switchTab(true)}
          >
            Sign Up
          </button>
        </div>

        <form onSubmit={handleSubmit} className="login-form" noValidate>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
            />
            {errors.email && <span className="form-error">{errors.email}</span>}
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
            {errors.password && <span className="form-error">{errors.password}</span>}
          </div>
          {isRegister && (
            <div className="form-group">
              <label htmlFor="confirmPw">Confirm Password</label>
              <input
                id="confirmPw"
                type="password"
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
                placeholder="••••••••"
              />
              {errors.confirmPw && <span className="form-error">{errors.confirmPw}</span>}
            </div>
          )}
          <button type="submit" className="login-submit">
            {isRegister ? 'Sign Up' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default LoginPage

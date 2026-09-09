import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [setupRequired, setSetupRequired] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function bootstrap() {
      try {
        const { setup_required } = await api.get('/auth/setup-required')
        setSetupRequired(setup_required)
        if (!setup_required) {
          try {
            setUser(await api.get('/auth/me'))
          } catch {
            setUser(null)
          }
        }
      } finally {
        setLoading(false)
      }
    }
    bootstrap()
  }, [])

  async function login(username, password) {
    const me = await api.post('/auth/login', { username, password })
    setUser(me)
  }

  async function setup(username, password) {
    const me = await api.post('/auth/setup', { username, password })
    setUser(me)
    setSetupRequired(false)
  }

  async function logout() {
    await api.post('/auth/logout')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, setupRequired, loading, login, setup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

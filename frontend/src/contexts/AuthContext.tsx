import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react"
import { api, setTokens, clearTokens, isAuthenticated, getAccessToken } from "../api/client"
import type { User } from "../types"

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, email?: string) => Promise<void>
  logout: () => void
  isAuth: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    clearTokens()
    setUser(null)
  }, [])

  useEffect(() => {
    if (!isAuthenticated()) {
      setLoading(false)
      return
    }
    api.me()
      .then(setUser)
      .catch(() => clearTokens())
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password)
    setTokens(res.access_token, res.refresh_token)
    setUser(res.user)
  }, [])

  const register = useCallback(async (username: string, password: string, email?: string) => {
    await api.register(username, password, email)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, isAuth: !!user }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}

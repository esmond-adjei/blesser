/* eslint-disable react/only-export-components -- context object and hook live with their provider */
import * as React from "react"
import * as api from "./api"
import { currentSubscription } from "./push"
import type { AuthUser } from "./types"

const REFRESH_KEY = "blesser.refresh_token"
/** Refresh this early so staggered pollers don't race the token's TTL. */
const REFRESH_MARGIN_MS = 60_000

interface AuthState {
  user: AuthUser | null
  /** False until the boot refresh settles; pages show a skeleton meanwhile. */
  ready: boolean
}

function accessExpiryMs(token: string | null): number | null {
  if (!token) return null
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: unknown }
    return typeof payload.exp === "number" ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

/** Access token in memory, refresh token in localStorage. Every refresh path
 * shares one single-flight; only a definitive 401 on the grant clears the session. */
const AuthContext = React.createContext<
  AuthState & {
    signIn: (email: string, password: string) => Promise<void>
    signUp: (email: string, password: string, acceptTerms: boolean) => Promise<void>
    signOut: () => Promise<void>
    updateUser: (user: AuthUser) => void
    /** Adopt a session minted by another sign-in method (OAuth). */
    adoptSession: (session: { user: AuthUser; tokens: { access_token: string; refresh_token: string } }) => void
  }
>({
  user: null,
  ready: false,
  signIn: () => Promise.reject(new Error("No provider")),
  signUp: () => Promise.reject(new Error("No provider")),
  signOut: () => Promise.reject(new Error("No provider")),
  updateUser: () => {},
  adoptSession: () => {},
})

export function useAuth() {
  return React.useContext(AuthContext)
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<AuthUser | null>(null)
  const [ready, setReady] = React.useState(false)
  const refreshFlight = React.useRef<Promise<string | null> | null>(null)
  // Bumped on session changes so the refresh timer reschedules.
  const [sessionSeq, setSessionSeq] = React.useState(0)

  const applySession = React.useCallback((next: { user: AuthUser; tokens: { access_token: string; refresh_token: string } }) => {
    try {
      localStorage.setItem(REFRESH_KEY, next.tokens.refresh_token)
    } catch {
      /* private mode — the session lasts until reload */
    }
    api.setAccessToken(next.tokens.access_token)
    setUser(next.user)
    setSessionSeq((n) => n + 1)
  }, [])

  const clearSession = React.useCallback(() => {
    try {
      localStorage.removeItem(REFRESH_KEY)
    } catch {
      /* storage unavailable */
    }
    api.setAccessToken(null)
    setUser(null)
    setSessionSeq((n) => n + 1)
  }, [])

  const doRefresh = React.useCallback(async (): Promise<string | null> => {
    let stored: string | null = null
    try {
      stored = localStorage.getItem(REFRESH_KEY)
    } catch {
      return null
    }
    if (!stored) return null
    try {
      const session = await api.refreshSession(stored)
      applySession(session)
      return session.tokens.access_token
    } catch (err) {
      // Only a definitive 401 kills the session; transient failures retry next tick.
      if (err instanceof api.ApiError && err.status === 401) clearSession()
      return null
    }
  }, [applySession, clearSession])

  // Single-flight refresh shared by the reactive 401 path and the timer.
  const refreshSoon = React.useCallback(() => {
    if (!refreshFlight.current) {
      refreshFlight.current = doRefresh().finally(() => {
        refreshFlight.current = null
      })
    }
    return refreshFlight.current
  }, [doRefresh])

  React.useEffect(() => {
    api.setRefreshHandler(refreshSoon)
    return () => api.setRefreshHandler(null)
  }, [refreshSoon])

  // Refresh before expiry, else some poller lands just past the TTL each cycle; 401 retry is the backstop.
  React.useEffect(() => {
    if (!user) return
    const delay = (accessExpiryMs(api.getAccessToken()) ?? 0) - Date.now() - REFRESH_MARGIN_MS
    if (delay <= 0) {
      void refreshSoon()
      return
    }
    const timer = window.setTimeout(() => void refreshSoon(), delay)
    return () => window.clearTimeout(timer)
  }, [user, sessionSeq, refreshSoon])

  // Boot: one silent refresh, then render (anon or restored).
  React.useEffect(() => {
    let live = true
    void doRefresh().finally(() => {
      if (live) setReady(true)
    })
    return () => {
      live = false
    }
  }, [doRefresh])

  const signIn = React.useCallback(
    async (email: string, password: string) => {
      applySession(await api.loginAccount(email, password))
    },
    [applySession],
  )

  const signUp = React.useCallback(
    async (email: string, password: string, acceptTerms: boolean) => {
      applySession(await api.registerAccount(email, password, acceptTerms))
    },
    [applySession],
  )

  const signOut = React.useCallback(async () => {
    let stored: string | null = null
    try {
      stored = localStorage.getItem(REFRESH_KEY)
    } catch {
      stored = null
    }
    // Drop this device's push subscription with the session, server- and browser-side.
    const pushSub = await currentSubscription()
    if (stored) {
      try {
        await api.logoutSession(stored, pushSub?.endpoint)
      } catch {
        /* already dead server-side — still sign out locally */
      }
    }
    await pushSub?.unsubscribe().catch(() => false)
    clearSession()
  }, [clearSession])

  const updateUser = React.useCallback((next: AuthUser) => setUser(next), [])

  const value = React.useMemo(
    () => ({ user, ready, signIn, signUp, signOut, updateUser, adoptSession: applySession }),
    [user, ready, signIn, signUp, signOut, updateUser, applySession],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

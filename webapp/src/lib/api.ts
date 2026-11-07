/** Typed fetch client for the backend; same-origin unless VITE_API_URL is set. */
import type {
  Application,
  ApplicationInput,
  AuthSession,
  AuthUser,
  CalendarFeed,
  Opportunity,
  OpportunityFacets,
  OpportunityQuery,
  OpportunitySubmit,
  Paged,
  Scan,
  ScanRequest,
  Todo,
  TodoCreate,
  TodoUpdate,
} from "./types"

export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? ""

export class ApiError extends Error {
  status: number
  body: string
  detail: unknown
  constructor(status: number, body: string, message?: string, detail?: unknown) {
    super(message ?? `Request failed (${status}): ${body.slice(0, 300)}`)
    this.name = "ApiError"
    this.status = status
    this.body = body
    this.detail = detail
  }
}

export function apiMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return "Something went wrong."
}

async function reqRaw(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  })
}

function parseDetail(text: string): { message: string; detail: unknown } {
  try {
    const parsed = JSON.parse(text) as { detail?: unknown }
    if (typeof parsed.detail === "string") return { message: parsed.detail, detail: parsed.detail }
    if (parsed.detail && typeof parsed.detail === "object") {
      const d = parsed.detail as { message?: unknown }
      if (typeof d.message === "string") return { message: d.message, detail: parsed.detail }
    }
  } catch {
    /* keep raw text */
  }
  return { message: text, detail: undefined }
}

// Token store lives here so every endpoint shares one token without import cycles.
let accessToken: string | null = null
let refreshHandler: (() => Promise<string | null>) | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

/** Current Bearer token for transports that can't use api.ts (e.g. the push service worker). */
export function getAccessToken(): string | null {
  return accessToken
}

export function setRefreshHandler(fn: (() => Promise<string | null>) | null) {
  refreshHandler = fn
}

// Auth endpoints manage their own credentials and never carry a token.
const TOKENLESS = new Set([
  "/api/auth/login",
  "/api/auth/register",
  "/api/auth/refresh",
  "/api/auth/password/forgot",
  "/api/auth/password/reset",
  "/api/auth/oauth/link",
  "/api/notifications/unsubscribe",
])

function authedInit(path: string, init?: RequestInit): RequestInit {
  if (accessToken && !TOKENLESS.has(path)) {
    return { ...init, headers: { ...(init?.headers ?? {}), Authorization: `Bearer ${accessToken}` } }
  }
  return init ?? {}
}

async function fetchWithAuth(
  path: string,
  init?: RequestInit,
): Promise<{ res: Response; text: string }> {
  let res = await reqRaw(path, authedInit(path, init))
  let text = await res.text()
  if (res.status === 401 && refreshHandler && !TOKENLESS.has(path)) {
    // One refresh then one replay on 401; the provider single-flights the refresh.
    const next = await refreshHandler()
    if (next) {
      res = await reqRaw(path, authedInit(path, init))
      text = await res.text()
    }
  }
  return { res, text }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const { res, text } = await fetchWithAuth(path, init)
  if (!res.ok) {
    const { message, detail } = parseDetail(text)
    throw new ApiError(res.status, text, message.slice(0, 500), detail)
  }
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

const get = <T>(path: string): Promise<T> => req<T>(path)
const post = <T>(path: string, body?: unknown): Promise<T> =>
  req<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })
const patch = <T>(path: string, body: unknown): Promise<T> =>
  req<T>(path, { method: "PATCH", body: JSON.stringify(body) })
const del = <T>(path: string, body?: unknown): Promise<T> =>
  req<T>(path, { method: "DELETE", body: body === undefined ? undefined : JSON.stringify(body) })

// --- Account -------------------------------------------------------------------

export const registerAccount = (email: string, password: string, acceptTerms: boolean) =>
  post<AuthSession>("/api/auth/register", { email, password, accept_terms: acceptTerms })
export const loginAccount = (email: string, password: string) =>
  post<AuthSession>("/api/auth/login", { email, password })
export const refreshSession = (refreshToken: string) =>
  post<AuthSession>("/api/auth/refresh", { refresh_token: refreshToken })
export const logoutSession = (refreshToken: string, pushEndpoint?: string | null) =>
  post<{ status: string }>("/api/auth/logout", { refresh_token: refreshToken, push_endpoint: pushEndpoint ?? null })
export const getMe = () => get<AuthUser>("/api/auth/me")
export interface OAuthProvider { id: string; label: string }
export interface OAuthLinkRequired { provider: string; email: string; link_token: string }
export type OAuthCallbackResult =
  | { user: AuthUser; tokens: { access_token: string; refresh_token: string }; next: string }
  | { link_required: OAuthLinkRequired; next: string }
export const oauthProviders = () => get<OAuthProvider[]>("/api/auth/oauth/providers")
export const oauthStart = (provider: string, next: string) =>
  post<{ authorize_url: string; state: string }>(`/api/auth/oauth/${provider}/start`, { next })
export const oauthCallback = (provider: string, code: string, state: string) =>
  post<OAuthCallbackResult>(`/api/auth/oauth/${provider}/callback`, { code, state })
export const oauthLink = (link_token: string, password: string) =>
  post<{ user: AuthUser; tokens: { access_token: string; refresh_token: string } }>("/api/auth/oauth/link", { link_token, password })
export const forgotPassword = (email: string) => post<{ status: string }>("/api/auth/password/forgot", { email })
export const resetPassword = (token: string, new_password: string) =>
  post<{ status: string }>("/api/auth/password/reset", { token, new_password })
export const verifyEmail = (token: string) => post<AuthUser>("/api/auth/verify", { token })
export const resendVerification = () => post<{ status: string }>("/api/auth/verify/send", {})
export const updateProfile = (display_name: string | null) => patch<AuthUser>("/api/auth/me", { display_name })
export const changePassword = (current_password: string, new_password: string) =>
  post<{ status: string }>("/api/auth/change-password", { current_password, new_password })
export const deleteAccount = (password: string) => del<{ status: string }>("/api/auth/account", { password })

// --- Opportunities (reads are public) --------------------------------------------

function query(params: object): string {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue
    q.set(key, String(value))
  }
  const text = q.toString()
  return text ? `?${text}` : ""
}

export const listOpportunities = (params: OpportunityQuery = {}) =>
  get<Paged<Opportunity>>(`/api/opportunities${query(params)}`)
export const getOpportunity = (id: string) => get<Opportunity>(`/api/opportunities/${id}`)
export const opportunityFacets = () => get<OpportunityFacets>("/api/opportunities/facets")
export const trackedOpportunities = () => get<Record<string, string>>("/api/opportunities/tracked")
export const trackOpportunity = (id: string) => post<Application>(`/api/opportunities/${id}/track`)
export const submitOpportunity = (body: OpportunitySubmit) => post<Opportunity>("/api/opportunities", body)
/** Absolute URL of one opportunity's .ics file (no auth needed). */
export const opportunityIcsUrl = (id: string) => `${API_BASE}/api/opportunities/${id}/calendar.ics`

// --- Applications ------------------------------------------------------------------

export const listApplications = () => get<Application[]>("/api/applications")
export const getApplication = (id: string) => get<Application>(`/api/applications/${id}`)
export const createApplication = (body: ApplicationInput & { title: string }) =>
  post<Application>("/api/applications", body)
export const updateApplication = (id: string, body: ApplicationInput) =>
  patch<Application>(`/api/applications/${id}`, body)
export const deleteApplication = (id: string) => del<{ status: string }>(`/api/applications/${id}`)

// --- To-dos and the calendar feed -------------------------------------------------

export const listTodos = (status: "open" | "done" | "all" = "open") => get<Todo[]>(`/api/todos?status=${status}`)
export const createTodo = (body: TodoCreate) => post<Todo>("/api/todos", body)
export const updateTodo = (id: string, body: TodoUpdate) => patch<Todo>(`/api/todos/${id}`, body)
export const deleteTodo = (id: string) => del<{ status: string }>(`/api/todos/${id}`)
export const getCalendarFeed = () => get<CalendarFeed>("/api/calendar/feed")
export const rotateCalendarFeed = () => post<CalendarFeed>("/api/calendar/feed/rotate")

// --- Scans ---------------------------------------------------------------------------

export const listScans = () => get<Scan[]>("/api/scans")
export const getScan = (id: string) => get<Scan>(`/api/scans/${id}`)
export const startScan = (body: ScanRequest) => post<Scan>("/api/scans", body)
export const cancelScan = (id: string) => post<Scan>(`/api/scans/${id}/cancel`)
export const deleteScan = (id: string) => del<{ status: string }>(`/api/scans/${id}`)

// --- Notifications ------------------------------------------------------------------

export type NotificationChannel = "inbox" | "push" | "email"
export interface AppNotification {
  id: string
  kind: string
  title: string
  body: string
  /** In-app path the notification opens. */
  link: string
  entity_id: string | null
  created_at: string
  read_at: string | null
}
export interface NotificationInbox {
  items: AppNotification[]
  unread: number
  /** Stored timezone; null until the browser reports one. */
  timezone: string | null
}
export interface NotificationKindPrefs {
  kind: string
  label: string
  description: string
  channels: Record<NotificationChannel, boolean>
  defaults: Record<NotificationChannel, boolean>
}
export interface NotificationPreferences {
  kinds: NotificationKindPrefs[]
  quiet_start: string | null
  quiet_end: string | null
  timezone: string | null
  email_digest: boolean
}
export interface NotificationPreferencesPatch {
  channels?: Record<string, Partial<Record<NotificationChannel, boolean>>>
  quiet_start?: string | null
  quiet_end?: string | null
  timezone?: string | null
  email_digest?: boolean
}
export interface PushDevice {
  id: string
  endpoint: string
  user_agent: string | null
  created_at: string
  last_ok_at: string | null
}
export const listNotifications = () => get<NotificationInbox>("/api/notifications")
export const deleteNotification = (id: string) => del<{ removed: number }>(`/api/notifications/${encodeURIComponent(id)}`)
export const clearNotifications = () => del<{ removed: number }>("/api/notifications")
export const markNotificationRead = (id: string) => post<{ marked: number }>(`/api/notifications/${id}/read`)
export const markAllNotificationsRead = () => post<{ marked: number }>("/api/notifications/read-all")
export const getNotificationPreferences = () => get<NotificationPreferences>("/api/notifications/preferences")
export const updateNotificationPreferences = (body: NotificationPreferencesPatch) =>
  patch<NotificationPreferences>("/api/notifications/preferences", body)
export const getPushConfig = () => get<{ enabled: boolean; public_key: string | null }>("/api/notifications/push/config")
export const listPushDevices = () => get<PushDevice[]>("/api/notifications/push/subscriptions")
export const savePushSubscription = (body: {
  endpoint: string
  keys: { p256dh: string; auth: string }
  timezone?: string
}) => post<PushDevice>("/api/notifications/push/subscriptions", body)
export const removePushSubscription = (endpoint: string) =>
  del<{ removed: number }>("/api/notifications/push/subscriptions", { endpoint })
export const sendTestNotification = () =>
  post<{ push_enabled: boolean; devices: number; pushed: number }>("/api/notifications/test")
export const sendTestEmail = () =>
  post<{ to: string; sent: boolean; backend: string }>("/api/notifications/test-email")
export const unsubscribeNotificationEmail = (token: string) =>
  post<{ status: string; kind: string; label: string }>("/api/notifications/unsubscribe", { token })


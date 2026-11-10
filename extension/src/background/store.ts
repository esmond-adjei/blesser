import type { Prefs, Review, Settings } from "../shared/types"

export interface Auth {
  access_token: string
  refresh_token: string
  session_id: string
}

export interface PendingConnect {
  state: string
  created: number
}

export interface Area {
  get(key: string): Promise<Record<string, unknown>>
  set(items: Record<string, unknown>): Promise<void>
  remove(key: string | string[]): Promise<void>
}

export const DEFAULT_SETTINGS: Settings = { apiUrl: __DEFAULT_API_URL__, appUrl: __DEFAULT_APP_URL__ }
export const DEFAULT_PREFS: Prefs = { fillAs: "me", allowDrafting: true }
const CONNECT_TTL_MS = 10 * 60_000

export const reviewKey = (tabId: number) => `review:${tabId}`

const trim = (url: string) => url.trim().replace(/\/+$/, "")

/** Tokens and settings in chrome.storage.local (trusted contexts only); per-tab results in session storage. */
export class Store {
  private local: Area
  private session: Area

  constructor(local: Area, session: Area) {
    this.local = local
    this.session = session
  }

  private async read<T>(area: Area, key: string): Promise<T | undefined> {
    return (await area.get(key))[key] as T | undefined
  }

  async settings(): Promise<Settings> {
    return { ...DEFAULT_SETTINGS, ...(await this.read<Settings>(this.local, "settings")) }
  }

  async saveSettings(next: Settings): Promise<Settings> {
    const before = await this.settings()
    const clean = { apiUrl: trim(next.apiUrl) || DEFAULT_SETTINGS.apiUrl, appUrl: trim(next.appUrl) || DEFAULT_SETTINGS.appUrl }
    for (const url of [clean.apiUrl, clean.appUrl]) {
      const parsed = new URL(url)
      if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("Use an http or https address.")
    }
    await this.local.set({ settings: clean })
    // Tokens belong to one API; a new address starts signed out.
    if (clean.apiUrl !== before.apiUrl) await this.local.remove("auth")
    return clean
  }

  async prefs(): Promise<Prefs> {
    return { ...DEFAULT_PREFS, ...(await this.read<Prefs>(this.local, "prefs")) }
  }

  savePrefs(prefs: Prefs) {
    return this.local.set({ prefs })
  }

  auth() {
    return this.read<Auth>(this.local, "auth")
  }

  saveAuth(auth: Auth) {
    return this.local.set({ auth })
  }

  clearAuth() {
    return this.local.remove("auth")
  }

  async beginConnect(state: string, now = Date.now()) {
    await this.local.set({ pending: { state, created: now } satisfies PendingConnect })
  }

  /** One-shot: the pending state is consumed whether or not it matches. */
  async takeConnect(state: string, now = Date.now()): Promise<boolean> {
    const pending = await this.read<PendingConnect>(this.local, "pending")
    await this.local.remove("pending")
    return !!pending && pending.state === state && now - pending.created < CONNECT_TTL_MS
  }

  private queue = new Map<number, Promise<unknown>>()

  review(tabId: number) {
    return this.read<Review>(this.session, reviewKey(tabId))
  }

  saveReview(review: Review) {
    return this.session.set({ [reviewKey(review.tabId)]: review })
  }

  dropReview(tabId: number) {
    return this.session.remove(reviewKey(tabId))
  }

  /** Read-modify-write of one tab's review, serialized so page events and panel actions don't overwrite each other. */
  updateReview(tabId: number, change: (review: Review) => Review | Promise<Review>): Promise<Review | undefined> {
    const run = (this.queue.get(tabId) ?? Promise.resolve()).catch(() => {}).then(async () => {
      const current = await this.review(tabId)
      if (!current) return undefined
      const next = await change(current)
      await this.saveReview(next)
      return next
    })
    this.queue.set(tabId, run)
    return run
  }
}

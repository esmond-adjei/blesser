import type { FormProgress, Prefs, ProgressField, Review, Settings } from "../shared/types"

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
export const progressKey = (tabId: number) => `progress:${tabId}`

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

  private queue = new Map<string, Promise<unknown>>()

  /** Runs read-modify-write steps on one key one after another, so concurrent events don't overwrite each other. */
  private serial<T>(key: string, step: () => Promise<T>): Promise<T> {
    const run = (this.queue.get(key) ?? Promise.resolve()).catch(() => {}).then(step)
    this.queue.set(key, run)
    return run
  }

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
    return this.serial(reviewKey(tabId), async () => {
      const current = await this.review(tabId)
      if (!current) return undefined
      const next = await change(current)
      await this.saveReview(next)
      return next
    })
  }

  progress(tabId: number) {
    return this.read<FormProgress>(this.session, progressKey(tabId))
  }

  saveProgress(progress: FormProgress) {
    return this.serial(progressKey(progress.tabId), () => this.session.set({ [progressKey(progress.tabId)]: progress }))
  }

  /** One frame's latest count; other frames keep theirs. */
  updateProgress(tabId: number, frameId: number, fields: ProgressField[]): Promise<FormProgress> {
    return this.serial(progressKey(tabId), async () => {
      const current = (await this.progress(tabId)) ?? { tabId, url: "", frames: {} }
      const next = { ...current, frames: { ...current.frames, [String(frameId)]: fields } }
      await this.session.set({ [progressKey(tabId)]: next })
      return next
    })
  }

  dropProgress(tabId: number) {
    return this.serial(progressKey(tabId), () => this.session.remove(progressKey(tabId)))
  }
}

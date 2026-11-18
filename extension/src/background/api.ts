import type { ExtensionMe, FillFeedback, FillRequest, FillResponse, ProblemReport, TrackedApplication } from "../shared/types"
import type { Store } from "./store"

const FILL_TIMEOUT_MS = 75_000

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export class SignedOut extends Error {
  constructor() {
    super("You're not connected to Blesser.")
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  const text = await res.text().catch(() => "")
  let message = text.slice(0, 300) || `Request failed (${res.status})`
  try {
    const detail = (JSON.parse(text) as { detail?: unknown }).detail
    if (typeof detail === "string") message = detail
    else if (Array.isArray(detail) && detail[0]?.msg) message = String(detail[0].msg)
    else if (detail && typeof detail === "object" && "message" in detail) message = String((detail as { message: unknown }).message)
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, message)
}

interface DocumentMeta {
  id: string
  filename: string
  content_type: string
}

export interface Application extends TrackedApplication {
  id: string
  status: string
  opportunity_id: string | null
}

/** All extension traffic: bearer tokens from the store, one single-flight refresh on 401. */
export class Api {
  private refreshing: Promise<string | null> | null = null
  private store: Store
  private fetcher: typeof fetch

  constructor(store: Store, fetcher: typeof fetch = (...args) => fetch(...args)) {
    this.store = store
    this.fetcher = fetcher
  }

  private async base() {
    return (await this.store.settings()).apiUrl
  }

  private async refresh(): Promise<string | null> {
    this.refreshing ??= (async () => {
      const auth = await this.store.auth()
      if (!auth) return null
      const res = await this.fetcher(`${await this.base()}/api/app/extension/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: auth.refresh_token }),
      })
      if (res.status === 401 || res.status === 403) {
        await this.store.clearAuth()
        return null
      }
      if (!res.ok) throw await errorFrom(res)
      const pair = (await res.json()) as { access_token: string; refresh_token: string }
      await this.store.saveAuth({ ...auth, ...pair })
      return pair.access_token
    })().finally(() => {
      this.refreshing = null
    })
    return this.refreshing
  }

  async raw(path: string, init: RequestInit = {}): Promise<Response> {
    const auth = await this.store.auth()
    if (!auth) throw new SignedOut()
    const send = (token: string) =>
      this.base().then((base) =>
        this.fetcher(`${base}${path}`, {
          ...init,
          headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers, Authorization: `Bearer ${token}` },
        }),
      )
    let res = await send(auth.access_token)
    if (res.status === 401) {
      const token = await this.refresh()
      if (!token) throw new SignedOut()
      res = await send(token)
      if (res.status === 401) {
        await this.store.clearAuth()
        throw new SignedOut()
      }
    }
    if (!res.ok) throw await errorFrom(res)
    return res
  }

  async json<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await this.raw(path, init)
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
  }

  me() {
    return this.json<ExtensionMe>("/api/app/extension/me")
  }

  async fill(body: FillRequest, timeoutMs = FILL_TIMEOUT_MS) {
    try {
      return await this.json<FillResponse>("/api/app/autofill/fill", { method: "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs) })
    } catch (err) {
      if (err instanceof DOMException && err.name === "TimeoutError")
        throw new Error(body.allow_drafting ? "Blesser took too long to answer. Try again, or turn off drafting for this page." : "Blesser took too long to answer. Try again.")
      throw err
    }
  }

  feedback(body: FillFeedback) {
    return this.json<void>("/api/app/autofill/feedback", { method: "POST", body: JSON.stringify(body) })
  }

  report(body: ProblemReport) {
    return this.json<void>("/api/app/autofill/reports", { method: "POST", body: JSON.stringify(body) })
  }

  applications() {
    return this.json<Application[]>("/api/app/applications")
  }

  markSubmitted(id: string) {
    return this.json<Application>(`/api/app/applications/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ status: "submitted" }) })
  }

  async download(documentId: string): Promise<{ name: string; type: string; base64: string }> {
    const res = await this.raw(`/api/app/documents/${encodeURIComponent(documentId)}/download`)
    const contentType = (res.headers.get("Content-Type") ?? "application/octet-stream").split(";")[0].trim()
    const disposition = res.headers.get("Content-Disposition") ?? ""
    const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(disposition)
    const plain = /filename="?([^";]+)"?/i.exec(disposition)
    let name = star ? decodeURIComponent(star[1].replace(/"/g, "")) : plain ? plain[1] : ""
    let type = contentType
    // Cross-origin fetches can't read Content-Disposition unless the API exposes it, so ask the library.
    if (!name || type === "application/octet-stream") {
      const meta = (await this.json<DocumentMeta[]>("/api/app/documents").catch(() => [])).find((d) => d.id === documentId)
      name ||= meta?.filename ?? `document-${documentId}`
      if (meta?.content_type) type = meta.content_type
    }
    const bytes = new Uint8Array(await res.arrayBuffer())
    let binary = ""
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
    return { name, type, base64: btoa(binary) }
  }

  async logout() {
    const auth = await this.store.auth()
    if (!auth) return
    try {
      await this.raw("/api/app/extension/logout", { method: "POST", body: JSON.stringify({ refresh_token: auth.refresh_token }) })
    } catch {
      /* the session may already be revoked from Settings */
    }
    await this.store.clearAuth()
  }
}

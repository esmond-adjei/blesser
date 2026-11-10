import { describe, expect, it, vi } from "vitest"
import { Api, SignedOut } from "../src/background/api"
import { acceptConnect, connectUrl } from "../src/background/connect"
import { blockedReason, runFill, type Scripting } from "../src/background/fill"
import { Store, type Area } from "../src/background/store"
import { counts } from "../src/shared/review"
import type { CollectedField, FillInstruction, FillRequest, FillResponse } from "../src/shared/types"

function memory(): Area & { data: Record<string, unknown> } {
  const data: Record<string, unknown> = {}
  return {
    data,
    get: async (key) => (key in data ? { [key]: structuredClone(data[key]) } : {}),
    set: async (items) => void Object.assign(data, structuredClone(items)),
    remove: async (keys) => void [keys].flat().forEach((k) => delete data[k]),
  }
}

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } })

async function signedIn() {
  const store = new Store(memory(), memory())
  await store.saveAuth({ access_token: "a1", refresh_token: "r1", session_id: "s1" })
  return store
}

const APP = "http://localhost:5173"
const payload = (state: string) => ({
  type: "blesser.connect",
  state,
  access_token: "acc",
  refresh_token: "ref",
  session: { id: "sess", name: "Chrome on Linux", created_at: "2026-11-10T00:00:00Z", last_used_at: null },
})

describe("connect handshake", () => {
  it("builds the app URL with the extension id and state", () => {
    expect(connectUrl(APP, "abcdefghijklmnopabcdefghijklmnop", "st8")).toBe(
      `${APP}/connect/extension?ext=abcdefghijklmnopabcdefghijklmnop&state=st8`,
    )
  })

  it("stores tokens only for the issued state from the app origin, once", async () => {
    const store = new Store(memory(), memory())
    await store.beginConnect("good")
    expect(await acceptConnect(store, payload("good"), "https://evil.example/connect/extension")).toEqual({ ok: false, error: "bad_origin" })
    expect(await store.auth()).toBeUndefined()
    expect(await acceptConnect(store, payload("good"), `${APP}/connect/extension?x=1`)).toEqual({ ok: true })
    expect(await store.auth()).toEqual({ access_token: "acc", refresh_token: "ref", session_id: "sess" })
    expect(await acceptConnect(store, payload("good"), APP)).toEqual({ ok: false, error: "state_mismatch" })
  })

  it("rejects a forged state, an expired one and malformed messages", async () => {
    const store = new Store(memory(), memory())
    await store.beginConnect("real")
    expect((await acceptConnect(store, payload("forged"), APP)).error).toBe("state_mismatch")
    await store.beginConnect("old", Date.now() - 11 * 60_000)
    expect((await acceptConnect(store, payload("old"), APP)).error).toBe("state_mismatch")
    expect((await acceptConnect(store, { type: "blesser.connect" }, APP)).error).toBe("bad_message")
    expect(await store.auth()).toBeUndefined()
  })
})

describe("Api", () => {
  it("refreshes once on 401, rotates the stored tokens and replays", async () => {
    const store = await signedIn()
    const calls: string[] = []
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url).replace("http://localhost:8000", "")
      const auth = new Headers(init?.headers).get("Authorization")
      calls.push(`${path} ${auth ?? ""}`)
      if (path === "/api/app/extension/refresh") return json(200, { access_token: "a2", refresh_token: "r2" })
      return auth === "Bearer a2" ? json(200, { user: { id: "u" }, projects: [], drafting: { enabled: true, remaining_today: 60 } }) : json(401, { detail: "expired" })
    })
    const api = new Api(store, fetcher as typeof fetch)
    const [a, b] = await Promise.all([api.me(), api.me()])
    expect(a.drafting.remaining_today).toBe(60)
    expect(b.user.id).toBe("u")
    expect(calls.filter((c) => c.startsWith("/api/app/extension/refresh"))).toHaveLength(1)
    expect(await store.auth()).toMatchObject({ access_token: "a2", refresh_token: "r2" })
  })

  it("signs out when the refresh token is revoked", async () => {
    const store = await signedIn()
    const fetcher = vi.fn(async () => json(401, { detail: "revoked" }))
    const api = new Api(store, fetcher as typeof fetch)
    await expect(api.me()).rejects.toBeInstanceOf(SignedOut)
    expect(await store.auth()).toBeUndefined()
  })

  it("downloads documents with their filename and type", async () => {
    const store = await signedIn()
    const fetcher = vi.fn(async () =>
      new Response(new Uint8Array([37, 80, 68, 70]), {
        status: 200,
        headers: { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="Ama CV.pdf"' },
      }),
    )
    const file = await new Api(store, fetcher as typeof fetch).download("d1")
    expect(file).toEqual({ name: "Ama CV.pdf", type: "application/pdf", base64: btoa("%PDF") })
  })

  it("clears tokens when the API address changes", async () => {
    const store = await signedIn()
    await store.saveSettings({ apiUrl: "http://localhost:8000/", appUrl: APP })
    expect(await store.auth()).toBeDefined()
    await store.saveSettings({ apiUrl: "https://api.blesser.example", appUrl: APP })
    expect(await store.auth()).toBeUndefined()
  })
})

const field = (key: string, label: string, extra: Partial<CollectedField> = {}): CollectedField => ({
  key, tag: "input", type: "text", name: "", id: "", autocomplete: "", label, placeholder: "", help_text: "", section: "",
  options: [], required: false, max_length: null, word_limit: null, accept: "", custom: false, ...extra,
})

describe("runFill", () => {
  it("merges frames, sends the contract shape, attaches documents and summarises", async () => {
    const store = await signedIn()
    let sent: FillRequest | null = null
    const response: FillResponse = {
      fills: [
        { key: "0:0", value: "Ama", document_id: null, source: "profile", confidence: "high", note: "" },
        { key: "0:1", value: null, document_id: "doc1", source: "document", confidence: "high", note: "" },
        { key: "7:0", value: "Solar cold rooms.", document_id: null, source: "drafted", confidence: "medium", note: "" },
        { key: "7:1", value: "Prototype", document_id: null, source: "project", confidence: "high", note: "" },
      ],
      unfilled: [{ key: "0:2", reason: "Nothing in your kit fits" }],
      matched_opportunity_id: "opp1",
      usage: { drafted_fields: 1, remaining_today: 59 },
    }
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      if (String(url).endsWith("/autofill/fill")) {
        sent = JSON.parse(String(init?.body))
        return json(200, response)
      }
      return new Response("cv", { headers: { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="cv.pdf"' } })
    })
    const filled: Record<number, FillInstruction[]> = {}
    const scripting: Scripting = {
      collect: async () => [
        { frameId: 0, result: [field("0", "First name", { required: true }), field("1", "CV", { type: "file" }), field("2", "Pronouns", { required: true })] },
        { frameId: 7, result: [field("0", "Problem", { tag: "textarea" }), field("1", "Stage", { type: "radio", custom: true })] },
      ],
      fill: async (_tab, frameId, list) => {
        filled[frameId] = list
        return list.map((i) =>
          i.key === "1" && frameId === 7
            ? { key: i.key, status: "skipped" as const, reason: "Pick this one yourself. Suggested: Prototype" }
            : { key: i.key, status: i.drafted ? ("drafted" as const) : ("filled" as const), reason: "" },
        )
      },
      write: async () => ({ ok: true, reason: "", value: null }),
    }
    const summary = await runFill(new Api(store, fetcher as typeof fetch), scripting, { id: 3, url: "https://boards.greenhouse.io/x/jobs/1", title: "Apply" }, { fillAs: "proj1", allowDrafting: false })

    expect(sent!.use).toEqual({ profile: true, project_id: "proj1" })
    expect(sent!.allow_drafting).toBe(false)
    expect(sent!.page).toEqual({ url: "https://boards.greenhouse.io/x/jobs/1", title: "Apply", host: "boards.greenhouse.io" })
    expect(sent!.fields.map((f) => f.key)).toEqual(["0:0", "0:1", "0:2", "7:0", "7:1"])
    expect(Object.keys(sent!.fields[0]).sort()).toEqual(
      ["accept", "autocomplete", "help_text", "id", "key", "label", "max_length", "name", "options", "placeholder", "required", "section", "tag", "type", "word_limit"],
    )
    expect(filled[0][1].file).toEqual({ name: "cv.pdf", type: "application/pdf", base64: btoa("cv") })
    expect(filled[7][0].drafted).toBe(true)
    expect(counts(summary)).toEqual({ filled: 2, drafted: 1, needs: 2 })
    expect(summary).toMatchObject({ host: "boards.greenhouse.io", matchedOpportunityId: "opp1", remainingToday: 59, moved: null })
    expect(summary.rows.filter((r) => r.status === "needs").map((n) => [n.key, n.label])).toEqual([["0:2", "Pronouns"], ["7:1", "Stage"]])
    const first = summary.rows.find((r) => r.key === "0:0")!
    expect(first).toMatchObject({ status: "filled", value: "Ama", filled: { value: "Ama", source: "profile", rule: null } })
    expect(summary.rows.find((r) => r.key === "0:1")).toMatchObject({ status: "filled", document: "cv.pdf" })
  })

  it("refuses browser pages and pages without fields", async () => {
    expect(blockedReason("chrome://extensions")).toMatch(/browser pages/)
    expect(blockedReason("https://chromewebstore.google.com/detail/x")).toMatch(/store/)
    expect(blockedReason("")).toMatch(/hasn.t let Blesser into this page.*Alt\+Shift\+F/)
    const store = await signedIn()
    const scripting: Scripting = { collect: async () => [{ frameId: 0, result: [] }], fill: async () => [], write: async () => ({ ok: true, reason: "", value: null }) }
    await expect(runFill(new Api(store), scripting, { id: 1, url: "https://example.org", title: "" }, { fillAs: "me", allowDrafting: true })).rejects.toThrow(/No form fields/)
  })
})

describe("document downloads across origins", () => {
  it("falls back to the document library when Content-Disposition is hidden by CORS", async () => {
    const store = await signedIn()
    const fetcher = vi.fn(async (url: string | URL | Request) =>
      String(url).endsWith("/api/app/documents")
        ? json(200, [{ id: "d1", filename: "Ama CV.pdf", content_type: "application/pdf" }])
        : new Response("pdf", { headers: { "Content-Type": "application/octet-stream" } }),
    )
    const file = await new Api(store, fetcher as typeof fetch).download("d1")
    expect(file).toMatchObject({ name: "Ama CV.pdf", type: "application/pdf" })
  })
})

describe("slow fills", () => {
  it("gives up with a clear message instead of hanging", async () => {
    const store = await signedIn()
    const fetcher = vi.fn((_url: string | URL | Request, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener("abort", () => reject(init.signal!.reason))),
    )
    const api = new Api(store, fetcher as unknown as typeof fetch)
    const body = { page: { url: "https://x.org", title: "", host: "x.org" }, use: { profile: true, project_id: null }, allow_drafting: true, fields: [] }
    await expect(api.fill(body, 20)).rejects.toThrow(/turn off drafting/)
  })
})

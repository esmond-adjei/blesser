import { describe, expect, it, vi } from "vitest"
import { Actions } from "../src/background/actions"
import { Api } from "../src/background/api"
import type { Scripting } from "../src/background/fill"
import { Store, type Area } from "../src/background/store"
import type { FieldDescriptor, ProblemReport, WriteResult } from "../src/shared/types"
import { descriptor, review, row } from "./rows"

function memory(): Area {
  const data: Record<string, unknown> = {}
  return {
    get: async (key) => (key in data ? { [key]: structuredClone(data[key]) } : {}),
    set: async (items) => void Object.assign(data, structuredClone(items)),
    remove: async (keys) => void [keys].flat().forEach((k) => delete data[k]),
  }
}

async function setup(write: (key: string, value: string | string[] | null) => WriteResult = (_k, v) => ({ ok: true, reason: "", value: v }), status = 204) {
  const store = new Store(memory(), memory())
  await store.saveAuth({ access_token: "a", refresh_token: "r", session_id: "s" })
  const gender = descriptor("0:1", "Gender", { tag: "select", type: "select", options: [{ value: "m", label: "Man" }, { value: "w", label: "Woman" }] })
  await store.saveReview(
    review([
      row("0:0", "First name"),
      row("0:1", "Gender", { field: gender, value: "m", rule: "concept:gender", filled: { value: "m", source: "profile", rule: "concept:gender" } }),
      row("2:0", "Country of birth", { value: "Ghana", rule: "inferred:nationality", confidence: "medium", filled: { value: "Ghana", source: "profile", rule: "inferred:nationality" } }),
    ]),
  )
  const sent: { path: string; body: unknown }[] = []
  const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    sent.push({ path: String(url).replace("http://localhost:8000", ""), body: init?.body ? JSON.parse(String(init.body)) : null })
    return new Response(status === 204 ? null : JSON.stringify({ detail: "Not found" }), { status })
  })
  const writes: [number, number, string, unknown][] = []
  const scripting: Scripting = {
    collect: async () => [{ frameId: 0, result: [{ ...descriptor("0", "Email"), custom: false }] }],
    fill: async () => [],
    write: async (tabId, frameId, key, value) => {
      writes.push([tabId, frameId, key, value])
      return write(key, value)
    },
  }
  return { store, sent, writes, actions: new Actions(new Api(store, fetcher as typeof fetch), store, scripting) }
}

describe("panel actions", () => {
  it("edit in place writes to the right frame, updates the review and sends the correction", async () => {
    const { actions, writes, sent, store } = await setup((_k, v) => ({ ok: true, reason: "", value: v === "w" ? "Woman" : v }))
    const { review: next, warning } = await actions.edit(4, "0:1", "w")
    expect(warning).toBeNull()
    expect(writes).toEqual([[4, 0, "1", "w"]])
    expect(next.rows[1]).toMatchObject({ status: "filled", value: "Woman", source: "member", rule: "correction" })
    expect((await store.review(4))!.rows[1].value).toBe("Woman")
    expect(sent).toEqual([
      {
        path: "/api/app/autofill/feedback",
        body: {
          page: { url: "https://apply.example.org/form?step=1", host: "apply.example.org" },
          field: expect.objectContaining({ key: "0:1", label: "Gender" }),
          filled: { value: "m", source: "profile", rule: "concept:gender" },
          corrected: { value: "Woman" },
        },
      },
    ])
  })

  it("doesn't send feedback when the value didn't change, and surfaces a page refusal", async () => {
    const { actions, sent } = await setup((_k, v) => (v !== "Atlantis" ? { ok: true, reason: "", value: v } : { ok: false, reason: "None of the options matched", value: null }))
    await actions.edit(4, "0:0", "Ama")
    expect(sent).toEqual([])
    await expect(actions.edit(4, "2:0", "Atlantis")).rejects.toThrow("None of the options matched")
  })

  it("wrong field clears the page and sends wrong_field", async () => {
    const { actions, writes, sent } = await setup()
    const { review: next } = await actions.wrongField(4, "2:0")
    expect(writes).toEqual([[4, 2, "0", null]])
    expect(next.rows[2].status).toBe("needs")
    expect(sent[0].body).toMatchObject({ field: { key: "2:0" }, filled: { value: "Ghana", rule: "inferred:nationality" }, corrected: { wrong_field: true } })
  })

  it("clear writes nothing to the API", async () => {
    const { actions, sent } = await setup()
    expect((await actions.clear(4, "0:0")).review.rows[0].status).toBe("needs")
    expect(sent).toEqual([])
  })

  it("a page edit is offered, then remembered as a correction", async () => {
    const { actions, sent, store } = await setup()
    await actions.fromPage(4, 0, { type: "blesser.edited", key: "1", value: "Woman" })
    expect((await store.review(4))!.rows[1].pageEdit).toEqual({ value: "Woman" })
    const { review: next } = await actions.remember(4, "0:1")
    expect(next.rows[1]).toMatchObject({ value: "Woman", pageEdit: null, source: "member" })
    expect(sent[0].body).toMatchObject({ corrected: { value: "Woman" }, filled: { value: "m" } })
  })

  it("keeps the page edit when remembering fails", async () => {
    const { actions, store } = await setup(undefined, 404)
    await actions.fromPage(4, 0, { type: "blesser.edited", key: "0", value: "Ama Serwaa" })
    const { warning } = await actions.remember(4, "0:0")
    expect(warning).toMatch(/couldn't remember it: Not found/)
    expect((await store.review(4))!.rows[0].pageEdit).toEqual({ value: "Ama Serwaa" })
  })

  it("marks the review when the page moves on", async () => {
    const { actions, store } = await setup()
    await actions.fromPage(4, 0, { type: "blesser.step", added: 3 })
    expect((await store.review(4))!.moved).toBe("step")
    await actions.navigated(4)
    expect((await store.review(4))!.moved).toBe("navigated")
  })

  it("reports send descriptors only, even if something tried to add values", async () => {
    const { actions, sent } = await setup()
    const preview = await actions.reportPreview({ id: 4, url: "https://apply.example.org/form", title: "Apply" })
    expect(preview.fields.map((f) => f.key)).toEqual(["0:0"])
    const tainted = { ...preview.fields[0], value: "ama@example.com", custom: false } as FieldDescriptor & { value: string }
    const report: ProblemReport = { ...preview, fields: [tainted], note: "  Gender picked Woman  " }
    await actions.report(report)
    const body = sent[0].body as ProblemReport
    expect(sent[0].path).toBe("/api/app/autofill/reports")
    expect(body.note).toBe("Gender picked Woman")
    expect(body.page).toEqual({ url: "https://apply.example.org/form", host: "apply.example.org", title: "Apply" })
    expect(JSON.stringify(body)).not.toContain("ama@example.com")
    expect(Object.keys(body.fields[0])).not.toContain("value")
  })
})

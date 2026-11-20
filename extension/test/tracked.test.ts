import { describe, expect, it, vi } from "vitest"
import { Actions } from "../src/background/actions"
import type { Api, Application } from "../src/background/api"
import type { Scripting } from "../src/background/fill"
import { Store, type Area } from "../src/background/store"
import type { PageMatch, Review } from "../src/shared/types"

function memory(): Area {
  const data: Record<string, unknown> = {}
  return {
    get: async (key) => (key in data ? { [key]: structuredClone(data[key]) } : {}),
    set: async (items) => void Object.assign(data, structuredClone(items)),
    remove: async (keys) => void [keys].flat().forEach((k) => delete data[k]),
  }
}

const APPS: Application[] = [
  { id: "app-manual", title: "Accra Women in Tech Fellowship", deadline: "30 Nov 2026", deadline_date: "2026-11-30", status: "preparing", opportunity_id: null },
  { id: "app-catalog", title: "Kumasi Founders Fund", deadline: "Rolling", deadline_date: null, status: "submitted", opportunity_id: "opp1" },
]

const TAB = { id: 5, url: "https://fellows.example.com/apply", title: "Apply" }

const review = (over: Partial<Review>): Review => ({
  tabId: 5, url: TAB.url, host: "fellows.example.com", title: "Apply", at: "2026-11-20T10:00:00Z", rows: [],
  matchedOpportunityId: null, applied: false, remainingToday: null, moved: null, ...over,
})

function setup(match: PageMatch | Error = { application_id: "app-manual", opportunity_id: null }) {
  const store = new Store(memory(), memory())
  const api = {
    match: vi.fn(async () => {
      if (match instanceof Error) throw match
      return match
    }),
    applications: vi.fn(async () => APPS),
    markSubmitted: vi.fn(async (id: string) => ({ ...APPS.find((a) => a.id === id)!, status: "submitted" })),
  }
  const actions = new Actions(api as unknown as Api, store, {} as Scripting)
  return { store, api, actions }
}

describe("tracked application", () => {
  it("asks Blesser before any fill and finds an application added by hand", async () => {
    const { api, actions } = setup()
    expect(await actions.tracked(TAB)).toEqual({ title: "Accra Women in Tech Fellowship", deadline: "30 Nov 2026", deadline_date: "2026-11-30", applied: false })
    expect(api.match).toHaveBeenCalledWith(TAB.url, "Apply")
  })

  it("uses the last fill's match, including reviews stored before application ids", async () => {
    const { store, api, actions } = setup()
    await store.saveReview(review({ matchedOpportunityId: "opp1" }))
    expect(await actions.tracked(TAB)).toMatchObject({ title: "Kumasi Founders Fund", applied: true })
    expect(api.match).not.toHaveBeenCalled()
  })

  it("asks again after the tab moved to another page", async () => {
    const { store, api, actions } = setup()
    await store.saveReview(review({ matchedOpportunityId: "opp1", moved: "navigated" }))
    expect(await actions.tracked(TAB)).toMatchObject({ title: "Accra Women in Tech Fellowship" })
    expect(api.match).toHaveBeenCalledOnce()
  })

  it("shows no match for pages it can't read, unknown pages and older APIs", async () => {
    const blocked = setup()
    expect(await blocked.actions.tracked({ ...TAB, url: "" })).toBeNull()
    expect(blocked.api.match).not.toHaveBeenCalled()
    expect(await setup({ application_id: null, opportunity_id: null }).actions.tracked(TAB)).toBeNull()
    expect(await setup(new Error("Not Found")).actions.tracked(TAB)).toBeNull()
  })

  it("marks the application as submitted once, and the review as applied", async () => {
    const { store, api, actions } = setup()
    await store.saveReview(review({ matchedApplicationId: "app-manual" }))
    expect(await actions.markApplied(TAB)).toMatchObject({ title: "Accra Women in Tech Fellowship", applied: true })
    expect(api.markSubmitted).toHaveBeenCalledWith("app-manual")
    expect((await store.review(5))?.applied).toBe(true)

    const done = setup({ application_id: "app-catalog", opportunity_id: "opp1" })
    await done.actions.markApplied(TAB)
    expect(done.api.markSubmitted).not.toHaveBeenCalled()
    await expect(setup({ application_id: null, opportunity_id: null }).actions.markApplied(TAB)).rejects.toThrow("This page isn't linked to an application you track.")
  })
})

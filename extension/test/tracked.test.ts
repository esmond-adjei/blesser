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
    updateApplication: vi.fn(async (id: string, body: { status: string }) => ({ ...APPS.find((a) => a.id === id)!, ...body })),
    createApplication: vi.fn(async (body: Record<string, unknown>) => ({ id: "app-new", opportunity_id: null, ...body }) as unknown as Application),
  }
  const actions = new Actions(api as unknown as Api, store, {} as Scripting)
  return { store, api, actions }
}

describe("tracked application", () => {
  it("asks Blesser before any fill and finds an application added by hand", async () => {
    const { api, actions } = setup()
    expect(await actions.tracked(TAB)).toEqual({ title: "Accra Women in Tech Fellowship", deadline: "30 Nov 2026", deadline_date: "2026-11-30", status: "preparing", applied: false })
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

  it("shows no match for pages it can't read or unknown pages, and stays unknown when the lookup fails", async () => {
    const blocked = setup()
    expect(await blocked.actions.tracked({ ...TAB, url: "" })).toBeNull()
    expect(blocked.api.match).not.toHaveBeenCalled()
    expect(await setup({ application_id: null, opportunity_id: null }).actions.tracked(TAB)).toBeNull()
    await expect(setup(new Error("Too many page lookups")).actions.tracked(TAB)).rejects.toThrow("Too many")
  })

  it("moving to Submitted marks the review as applied; the same status sends nothing", async () => {
    const { store, api, actions } = setup()
    await store.saveReview(review({ matchedApplicationId: "app-manual" }))
    expect(await actions.setStatus(TAB, "submitted")).toMatchObject({ title: "Accra Women in Tech Fellowship", status: "submitted", applied: true })
    expect(api.updateApplication).toHaveBeenCalledWith("app-manual", { status: "submitted" })
    expect((await store.review(5))?.applied).toBe(true)

    const done = setup({ application_id: "app-catalog", opportunity_id: "opp1" })
    await done.actions.setStatus(TAB, "submitted")
    expect(done.api.updateApplication).not.toHaveBeenCalled()
    await expect(setup({ application_id: null, opportunity_id: null }).actions.setStatus(TAB, "saved")).rejects.toThrow("This page isn't linked to an application you track.")
  })

  it("moves the application to the status the member picks", async () => {
    const { api, actions } = setup()
    expect(await actions.setStatus(TAB, "interview")).toMatchObject({ status: "interview", applied: true })
    expect(api.updateApplication).toHaveBeenCalledWith("app-manual", { status: "interview" })
  })
})

describe("save to my applications", () => {
  const input = { title: "  Accra Climate Prize ", organization: "Green Ghana", link: "ignored", deadline: "30 Nov 2026", deadline_date: "2026-11-30", status: "preparing" as const }

  it("creates the application with the page as its link and links the review", async () => {
    const { store, api, actions } = setup({ application_id: null, opportunity_id: null })
    await store.saveReview(review({}))
    expect(await actions.saveApplication(TAB, input)).toMatchObject({ title: "Accra Climate Prize", status: "preparing", applied: false })
    expect(api.createApplication).toHaveBeenCalledWith({
      title: "Accra Climate Prize", organization: "Green Ghana", link: TAB.url, deadline: "30 Nov 2026", deadline_date: "2026-11-30", status: "preparing",
    })
    expect((await store.review(5))?.matchedApplicationId).toBe("app-new")
  })

  it("refuses duplicates, empty titles, bad statuses and pages it can't read", async () => {
    await expect(setup().actions.saveApplication(TAB, input)).rejects.toThrow("already in your applications")
    const none = setup({ application_id: null, opportunity_id: null })
    await expect(none.actions.saveApplication(TAB, { ...input, title: " " })).rejects.toThrow("Add a title")
    await expect(none.actions.saveApplication(TAB, { ...input, status: "won" as never })).rejects.toThrow("Choose a status")
    await expect(none.actions.saveApplication({ ...TAB, url: "chrome://newtab" }, input)).rejects.toThrow("Open the application form first.")
    expect(none.api.createApplication).not.toHaveBeenCalled()
    await none.actions.saveApplication(TAB, { ...input, deadline_date: "next week" })
    expect(none.api.createApplication).toHaveBeenLastCalledWith(expect.objectContaining({ deadline_date: null }))
  })
})

// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { Markdown } from "./Markdown"
import { citationIndex, type CitationSource } from "../../lib/citations"

vi.mock("../../lib/queries", async importOriginal => ({
  ...await importOriginal<typeof import("../../lib/queries")>(),
  useCandidate: () => ({
    data: {
      id: "c1", run_id: "r1", professor_id: "p1", program_id: "g1", school_id: "s1",
      professor_name: "Ada Lovelace", school_name: "MIT", program_name: "Robotics",
      professor_photo_url: null, similarity_score: 0.91, rationale: "Works on soft robotics",
      status: "approved", draft_id: null, draft_subject: null, draft_body: null,
      draft_created_at: null, draft_count: 0, papers: [], draft_task_id: null, draft_task_status: null,
    },
    isLoading: false,
  }),
}))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
const source: CitationSource = { key: "s1", kind: "candidate", id: "c1", title: "Ada Lovelace", href: "/dossier/c1" }
let host: HTMLDivElement
let root: Root
beforeEach(async () => {
  vi.useFakeTimers()
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => root.render(<MemoryRouter><Markdown text="Read Ada [s1]." citations={citationIndex("Read Ada [s1].", { s1: source })} /></MemoryRouter>))
})
afterEach(async () => { await act(async () => root.unmount()); vi.useRealTimers(); host.remove(); document.body.innerHTML = "" })

it("previews a cited candidate with the full professor card", async () => {
  await act(async () => {
    host.querySelector<HTMLButtonElement>("[data-citation=s1]")?.focus()
    vi.advanceTimersByTime(200)
  })
  const preview = document.querySelector('[role="dialog"]')
  expect(preview?.querySelector('[aria-label="Open Ada Lovelace"]')).not.toBeNull()
  expect(preview?.textContent).toContain("Robotics")
  expect(preview?.textContent).toContain("Works on soft robotics")
  expect(preview?.textContent).toContain("91")
})

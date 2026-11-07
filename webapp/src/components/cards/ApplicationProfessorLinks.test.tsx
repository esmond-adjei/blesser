// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { blankApplication } from "../../lib/applications"
import { ApplicationDetail } from "./ApplicationCards"

const open = vi.fn()
vi.mock("../../lib/queries", () => ({
  useCandidate: () => ({ data: null }),
  useProfessor: (id: string | null) => ({ data: id === "p3" ? {
    id: "p3", name: "Profile professor", program_id: "g1", program_name: "Robotics",
    school_name: "Example University", lab_name: null, photo_url: "https://example.com/photo.jpg",
    bio: "Studies walking robots", papers: [],
  } : null }),
}))
vi.mock("../applications/ApplicationSchoolLink", () => ({ ApplicationSchoolLink: ({ name }: { name: string }) => name }))
vi.mock("../layout/openRecord", () => ({ useOpenRecord: () => ({ open, isOpen: () => false }) }))
vi.mock("../gradis/useFindPapers", () => ({ useFindPapers: () => ({ findPapers: vi.fn(), sending: false }) }))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

it("opens a saved professor without a candidate and a candidate when one exists", async () => {
  const host = document.createElement("div")
  document.body.appendChild(host)
  const root = createRoot(host)
  const app = { ...blankApplication(), id: "a1", createdAt: "", updatedAt: "", professors: [
    { name: "Saved professor", professorId: "p1" },
    { name: "Matched professor", professorId: "p2", candidateId: "c2" },
    { name: "Unknown professor" },
  ] }
  await act(async () => root.render(<MemoryRouter><ApplicationDetail app={app} size="page" onEdit={vi.fn()} onDelete={vi.fn()} onToggleRequirement={vi.fn()} onResolve={vi.fn()} /></MemoryRouter>))
  const buttons = [...host.querySelectorAll<HTMLButtonElement>("button")]
  await act(async () => buttons.find((b) => b.getAttribute("aria-label") === "Open Saved professor")?.click())
  expect(open).toHaveBeenCalledWith({ kind: "professor", id: "p1" }, "Saved professor")
  await act(async () => buttons.find((b) => b.getAttribute("aria-label") === "Open Matched professor")?.click())
  expect(open).toHaveBeenCalledWith({ kind: "candidate", id: "c2" }, "Matched professor")
  expect(host.textContent).toContain("Not in your research yet")
  expect(host.textContent).not.toContain("Requirements")
  expect(host.textContent).not.toContain("Fee waiver")
  expect(host.textContent).not.toContain("Funding")
  await act(async () => root.unmount())
  host.remove()
})

it("shows the saved professor's photo and bio in the listing card", async () => {
  const host = document.createElement("div")
  document.body.appendChild(host)
  const root = createRoot(host)
  const app = { ...blankApplication(), id: "a1", createdAt: "", updatedAt: "", professors: [{ name: "Profile professor", professorId: "p3" }] }
  await act(async () => root.render(<MemoryRouter><ApplicationDetail app={app} size="page" onEdit={vi.fn()} onDelete={vi.fn()} onToggleRequirement={vi.fn()} onResolve={vi.fn()} /></MemoryRouter>))
  expect(host.querySelector('img[src="https://example.com/photo.jpg"]')).not.toBeNull()
  expect(host.textContent).toContain("Studies walking robots")
  const link = host.querySelector<HTMLAnchorElement>('a[href="/professors/p3"]')
  expect(link).not.toBeNull()
  await act(async () => link?.click())
  expect(open).toHaveBeenCalledWith({ kind: "professor", id: "p3" }, "Profile professor")
  await act(async () => root.unmount())
  host.remove()
})

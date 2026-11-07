// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { SchoolDetailView } from "./SchoolDetailView"

vi.mock("../../lib/queries", () => ({
  useAllRunSchools: () => ({ items: [{ school: { id: "s1", name: "Example University", programs: [
    { id: "p1", name: "Engineering", department_url: "https://example.edu/engineering" }, { id: "p2", name: "Science", department_url: null },
  ] }, runIds: [], runId: "r1" }], isLoading: false }),
  useRuns: () => ({ data: [] }),
  useSchoolFaculty: () => ({ isLoading: false, data: [
    { id: "f1", name: "Ada", program_id: "p1", papers: 1, candidate_id: "c1", similarity_score: 0.9 },
    { id: "f2", name: "Grace", program_id: "p2", papers: 0, candidate_id: null },
  ] }),
}))
vi.mock("../../lib/applications", () => ({
  useApplications: () => ({ apps: [{ id: "a1", school: "Example University", program: "PhD", status: "applying", requirements: [], professors: [], deadline: "" }], isLoading: false }),
}))
vi.mock("../layout/openRecord", () => ({ useOpenRecord: () => ({ open: vi.fn(), isOpen: () => false }) }))
vi.mock("../gradis/useFindPapers", () => ({ useFindPapers: () => ({ findPapers: vi.fn(), sending: false }) }))

it("shows applications first and groups matched and unmatched professors by programme", () => {
  const html = renderToStaticMarkup(<MemoryRouter><SchoolDetailView schoolId="s1" size="page" /></MemoryRouter>)
  const doc = new DOMParser().parseFromString(html, "text/html")
  const sections = [...doc.querySelectorAll("section")]
  expect(sections.map((section) => section.querySelector("h3")?.textContent)).toEqual([
    "Your applications1", "Engineering", "Science",
  ])
  expect(sections[1].textContent).toContain("1 professor")
  expect(sections[1].textContent).toContain("Ada")
  expect(sections[1].textContent).not.toContain("Grace")
  expect(sections[2].textContent).toContain("Grace")
  expect(sections[1].querySelector('a[href="https://example.edu/engineering"]')?.textContent).toBe("Engineering")
  expect(sections[2].querySelector("h3")?.querySelector("a")).toBeNull()
})

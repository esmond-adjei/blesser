// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { ApplicationSchoolLink } from "./ApplicationSchoolLink"

vi.mock("../../lib/queries", () => ({
  useAllRunSchools: () => ({ items: [
    { school: { id: "s1", name: "Example University" } },
    { school: { id: "s2", name: "Shared Name" } },
    { school: { id: "s3", name: "Shared Name" } },
  ] }),
}))

function render(name: string) {
  const html = renderToStaticMarkup(<MemoryRouter><ApplicationSchoolLink name={name} /></MemoryRouter>)
  return new DOMParser().parseFromString(html, "text/html")
}

it("links a uniquely matched school and leaves missing or ambiguous names as text", () => {
  expect(render(" example university ").querySelector("a")?.getAttribute("href")).toBe("/schools/s1")
  expect(render("Unknown").body.textContent).toBe("Unknown")
  expect(render("Shared Name").querySelector("a")).toBeNull()
})

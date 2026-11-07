// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { SchoolRowMenu } from "./SchoolCard"
import { ApplicationEditMenu } from "../applications/ApplicationEditMenu"
import { blankApplication } from "../../lib/applications"

vi.mock("../dialogs/ProspectDialogs", () => ({ SchoolDialog: () => <div role="dialog">School editor</div> }))
vi.mock("../dialogs/ApplicationWizard", () => ({ ApplicationWizard: () => <div role="dialog">Application editor</div> }))
vi.mock("../../lib/applications", async (original) => ({
  ...await original<typeof import("../../lib/applications")>(),
  useApplications: () => ({ upsert: vi.fn() }),
}))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

it.each(["school", "application"] as const)("opens the %s editor from the header menu", async (kind) => {
  const host = document.createElement("div")
  document.body.appendChild(host)
  const root = createRoot(host)
  const school = { id: "s1", name: "Example University", country: null, website_url: null, programs: [] }
  const app = { ...blankApplication(), id: "a1", school: "Example University", createdAt: "", updatedAt: "" }
  await act(async () => root.render(<MemoryRouter>{kind === "school" ? <SchoolRowMenu school={school} variant="header" /> : <ApplicationEditMenu app={app} variant="header" />}</MemoryRouter>))
  await act(async () => host.querySelector("button")?.click())
  const edit = [...document.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')].find((item) => item.textContent?.includes("Edit"))
  expect(edit).toBeDefined()
  await act(async () => edit?.click())
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain(kind === "school" ? "School editor" : "Application editor")
  await act(async () => root.unmount())
  host.remove()
})

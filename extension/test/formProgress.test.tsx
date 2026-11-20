// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { afterEach, describe, expect, it } from "vitest"
import type { FormProgress, ProgressField } from "../src/shared/types"
import { FormProgressCard } from "../src/sidepanel/FormProgress"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const f = (label: string, filled: boolean, section: string, required = false): ProgressField => ({ key: label, label, section, required, filled })

function render(progress: FormProgress) {
  const host = document.createElement("div")
  document.body.append(host)
  const root = createRoot(host)
  act(() => root.render(<FormProgressCard tabId={1} progress={progress} onSaved={() => {}} />))
  return { host, root }
}

afterEach(() => {
  document.body.innerHTML = ""
})

describe("FormProgressCard", () => {
  it("shows the share filled, required fields left and each section", () => {
    const { host, root } = render({
      tabId: 1,
      url: "https://a.example/",
      frames: { "0": [f("Name", true, "About you", true), f("Email", false, "About you", true), f("Pitch", true, "Venture")] },
    })
    const bar = host.querySelector('[role="progressbar"]')!
    expect(bar.getAttribute("aria-valuenow")).toBe("2")
    expect(bar.getAttribute("aria-valuemax")).toBe("3")
    expect(host.textContent).toContain("67%")
    expect(host.textContent).toContain("2 of 3 fields filled. 1 required field left.")
    const rows = Array.from(host.querySelectorAll('[aria-label="Sections"] li')).map((li) => li.textContent)
    expect(rows).toEqual(["About you1 of 2", "Venture1 of 1"])
    expect(host.querySelector("button")?.textContent).toBe("Download as Word")
    act(() => root.unmount())
  })

  it("hides the section list before anything is filled, and renders nothing for a page with no fields", () => {
    const { host } = render({ tabId: 1, url: "", frames: { "0": [f("Name", false, "A", true), f("Pitch", false, "B")] } })
    expect(host.textContent).toContain("0 of 2 fields filled. 1 required field left.")
    expect(host.querySelector('[aria-label="Sections"]')).toBeNull()
    const empty = render({ tabId: 1, url: "", frames: { "0": [] } })
    expect(empty.host.innerHTML).toBe("")
  })

  it("says when every required field is filled", () => {
    const { host } = render({ tabId: 1, url: "", frames: { "0": [f("Name", true, "", true), f("Pitch", false, "")] } })
    expect(host.textContent).toContain("1 of 2 fields filled. All required fields are filled.")
  })
})

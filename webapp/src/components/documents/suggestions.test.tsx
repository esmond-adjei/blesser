// @vitest-environment jsdom
import * as React from "react"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { CvSuggestion } from "../../lib/types"
import { SelectionBar } from "./SelectionBar"
import { SuggestionsPanel } from "./SuggestionsPanel"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

const render = (el: React.ReactElement) => act(() => root.render(el))
const buttons = () => [...host.querySelectorAll("button")].map((b) => b.textContent?.trim())
const button = (label: string) => [...host.querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement
const click = (el: HTMLElement) => act(() => el.dispatchEvent(new MouseEvent("click", { bubbles: true })))

function bar(props: Partial<React.ComponentProps<typeof SelectionBar>> = {}) {
  return (
    <SelectionBar
      text="Built tools"
      focus={false}
      saved
      tailorFor={null}
      saving={false}
      onAsk={() => {}}
      onSave={() => {}}
      onClose={() => {}}
      {...props}
    />
  )
}

describe("SelectionBar", () => {
  it("offers the quick changes, Tailor only for a tailored CV", () => {
    const onAsk = vi.fn()
    render(bar({ onAsk }))
    expect(buttons().slice(0, 3)).toEqual(["Improve", "Shorten", "Quantify"])
    expect(buttons().some((b) => b?.startsWith("Tailor"))).toBe(false)
    click(button("Shorten"))
    expect(onAsk).toHaveBeenCalledWith("shorten")

    render(bar({ onAsk, tailorFor: "Prof. Ada" }))
    click(button("Tailor to Prof. Ada"))
    expect(onAsk).toHaveBeenLastCalledWith("tailor")
  })

  it("sends the student's own request", () => {
    const onAsk = vi.fn()
    render(bar({ onAsk }))
    const input = host.querySelector("input") as HTMLInputElement
    act(() => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set
      set?.call(input, "Make it punchier")
      input.dispatchEvent(new Event("input", { bubbles: true }))
    })
    act(() => (host.querySelector("form") as HTMLFormElement).requestSubmit())
    expect(onAsk).toHaveBeenCalledWith("custom", "Make it punchier")
  })

  it("asks an unsaved variant to be saved first", () => {
    const onSave = vi.fn()
    render(bar({ saved: false, onSave }))
    expect(host.textContent).toContain("Save to get suggestions")
    expect(buttons()).toEqual(["Save"])
    click(button("Save"))
    expect(onSave).toHaveBeenCalled()
  })
})

function suggestion(id: string, extra: Partial<CvSuggestion> = {}): CvSuggestion {
  return {
    id,
    document_id: "d",
    version_id: null,
    find: `old ${id}`,
    replace: `new ${id}`,
    rationale: null,
    claim_check: { passed: true, new_terms: [] },
    limit_check: null,
    status: "pending",
    applicable: true,
    superseded_by: null,
    created_by: "editor",
    created_at: null,
    resolved_at: null,
    ...extra,
  }
}

function panel(props: Partial<React.ComponentProps<typeof SuggestionsPanel>> = {}) {
  return (
    <SuggestionsPanel
      suggestions={[]}
      requests={[]}
      busyId={null}
      activeId={null}
      applyingAll={false}
      onAccept={() => {}}
      onReject={() => {}}
      onLocate={() => {}}
      onApplyAll={() => {}}
      onRefresh={() => {}}
      onClose={() => {}}
      emptyHint="Select text and choose a change."
      {...props}
    />
  )
}

describe("SuggestionsPanel", () => {
  it("shows a row for a suggestion on its way, newest suggestions first", () => {
    render(panel({ requests: [{ id: "r", label: "Improve", excerpt: "Built tools" }], suggestions: [suggestion("a"), suggestion("b")] }))
    expect(host.querySelector('[role="status"]')?.textContent).toContain("Improve…")
    const befores = [...host.querySelectorAll("button[data-tooltip='Show in the text']")].map((b) => b.textContent)
    expect(befores.filter((t) => t?.startsWith("old"))).toEqual(["old b", "old a"])
  })

  it("offers Apply all only for more than one", () => {
    render(panel({ suggestions: [suggestion("a")] }))
    expect(buttons()).not.toContain("Apply all")
    const onApplyAll = vi.fn()
    // Not when they need their new words checked one by one.
    const flagged = { claim_check: { passed: false, new_terms: ["rust"] } }
    render(panel({ suggestions: [suggestion("a", flagged), suggestion("b", flagged)], onApplyAll }))
    expect(buttons()).not.toContain("Apply all")
    render(panel({ suggestions: [suggestion("a"), suggestion("b")], onApplyAll }))
    click(button("Apply all"))
    expect(onApplyAll).toHaveBeenCalled()
  })

  it("marks a suggestion's text when clicked, and applies or dismisses it", () => {
    const onLocate = vi.fn()
    const onAccept = vi.fn()
    const onReject = vi.fn()
    const s = suggestion("a")
    render(panel({ suggestions: [s], onLocate, onAccept, onReject }))
    click(button("old a"))
    expect(onLocate).toHaveBeenCalledWith(s)
    click(button("Apply"))
    expect(onAccept).toHaveBeenCalledWith(s, { replace: undefined, confirm: false })
    click(button("Dismiss"))
    expect(onReject).toHaveBeenCalledWith(s)
  })

  it("shows a stale suggestion disabled, with a way to ask for a fresh one", () => {
    const onRefresh = vi.fn()
    const onAccept = vi.fn()
    const onReject = vi.fn()
    // Its text was edited (no longer applicable), and one already marked stale.
    const edited = suggestion("a", { applicable: false })
    const stale = suggestion("b", { status: "stale", applicable: false })
    const replaced = suggestion("c", { status: "stale", applicable: false, superseded_by: "d" })
    render(panel({ suggestions: [edited, stale, replaced], onRefresh, onAccept, onReject }))
    expect(buttons()).not.toContain("Apply")
    expect(host.querySelectorAll("[aria-disabled]").length).toBe(2)
    expect(host.textContent).toContain("The text it changes was edited.")
    const fresh = [...host.querySelectorAll("button")].filter((b) => b.textContent?.includes("Get a fresh suggestion"))
    expect(fresh.length).toBe(2)
    click(fresh[0] as HTMLButtonElement)
    expect(onRefresh).toHaveBeenCalledWith(edited)
    // One asked for again leaves the list for the history.
    expect(host.textContent).toContain("asked again")
    expect(onAccept).not.toHaveBeenCalled()
  })

  it("marks a small change in place rather than showing two copies", () => {
    render(panel({ suggestions: [suggestion("a", { find: "Built tools for the lab", replace: "Built three tools for the lab" })] }))
    const change = host.querySelectorAll("button[data-tooltip='Show in the text']")
    expect(change.length).toBe(1)
    expect(change[0].querySelector("ins")?.textContent).toBe("three ")
    expect(change[0].querySelector("del")).toBeNull()
  })

  it("says how to ask when nothing is waiting", () => {
    render(panel())
    expect(host.textContent).toContain("No suggestions waiting.")
    expect(host.textContent).toContain("Select text and choose a change.")
  })
})

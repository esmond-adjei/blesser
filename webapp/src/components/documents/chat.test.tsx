// @vitest-environment jsdom
import * as React from "react"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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
const button = (label: string) =>
  [...host.querySelectorAll("button")].find((b) => b.textContent?.trim() === label || b.getAttribute("aria-label") === label) as HTMLButtonElement
const click = (el: HTMLElement) => act(() => el.dispatchEvent(new MouseEvent("click", { bubbles: true })))
describe("the chat's way in", () => {
  it("is a tab beside Review, which stays the default", () => {
    const onTab = vi.fn()
    render(
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
        emptyHint="Select text."
        onTab={onTab}
        chat={<p>the chat</p>}
      />,
    )
    const tabs = [...host.querySelectorAll('[role="tab"]')]
    expect(tabs.map((t) => t.textContent)).toEqual(["Review", "Chat"])
    expect(tabs[0].getAttribute("aria-selected")).toBe("true")
    click(tabs[1] as HTMLElement)
    expect(onTab).toHaveBeenCalledWith("chat")
  })

  it("is offered on a selection", () => {
    const onChat = vi.fn()
    render(<SelectionBar text="Built tools" focus={false} saved tailorFor={null} saving={false} onAsk={() => {}} onChat={onChat} onSave={() => {}} onClose={() => {}} />)
    click(button("Ask in chat"))
    expect(onChat).toHaveBeenCalled()
  })
})

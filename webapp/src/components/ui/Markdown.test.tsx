// @vitest-environment jsdom
import { act } from "react"
import { createRoot } from "react-dom/client"
import { expect, it, vi } from "vitest"
import { Markdown } from "./Markdown"

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

it("copies a fenced code block verbatim and leaves inline code alone", async () => {
  const writeText = vi.fn(async () => {})
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } })
  const host = document.createElement("div")
  document.body.appendChild(host)
  const root = createRoot(host)
  try {
    await act(async () => { root.render(<Markdown text={'Inline `example`.\n\n```python\nprint("hello")\nprint(2)\n```'} />) })
    const buttons = host.querySelectorAll("button")
    expect(buttons).toHaveLength(1)
    expect(buttons[0].getAttribute("aria-label")).toBe("Copy code")
    await act(async () => buttons[0].click())
    expect(writeText).toHaveBeenCalledExactlyOnceWith('print("hello")\nprint(2)\n')
    expect(buttons[0].getAttribute("aria-label")).toBe("Code copied")
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})

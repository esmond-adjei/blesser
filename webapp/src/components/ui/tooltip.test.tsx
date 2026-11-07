// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { createPortal } from "react-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "./tooltip"
import { Button } from "./button"

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

describe("app tooltips", () => {
  let host: HTMLDivElement
  let root: Root
  const tip = () => document.querySelector<HTMLElement>('[role="tooltip"]')
  const button = () => host.querySelector<HTMLButtonElement>("button")!
  async function render(content = <Button data-tooltip="Copy the subject and message" aria-describedby="existing"><span>Copy email</span></Button>) {
    await act(async () => { root.render(<TooltipProvider>{content}</TooltipProvider>) })
  }
  async function hover(target: Element = button(), pointerType = "mouse") {
    await act(async () => {
      const event = new MouseEvent("pointerover", { bubbles: true })
      Object.defineProperty(event, "pointerType", { value: pointerType })
      target.dispatchEvent(event)
    })
  }
  async function advance(ms = 450) {
    await act(async () => { vi.advanceTimersByTime(ms) })
  }
  beforeEach(() => {
    vi.useFakeTimers()
    host = document.createElement("div")
    document.body.appendChild(host)
    root = createRoot(host)
  })
  afterEach(async () => {
    await act(async () => { root.unmount() })
    host.remove()
    vi.useRealTimers()
  })

  it("shows a delayed description for nested icons and preserves existing descriptions", async () => {
    await render()
    await hover(button().querySelector("span")!)
    await advance(449)
    expect(tip()).toBeNull()
    await advance(1)
    expect(tip()?.textContent).toBe("Copy the subject and message")
    expect(button().getAttribute("aria-describedby")).toBe(`existing ${tip()!.id}`)
    await act(async () => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })) })
    expect(tip()).toBeNull()
    expect(button().getAttribute("aria-describedby")).toBe("existing")
  })

  it("shows labelled icon buttons on keyboard focus and dismisses on blur", async () => {
    await render(<button aria-label="Close suggestions" data-tooltip="Close suggestions">×</button>)
    await act(async () => { button().focus() })
    await advance(0)
    expect(tip()?.textContent).toBe("Close suggestions")
    await act(async () => { button().blur() })
    expect(tip()).toBeNull()
    expect(button().hasAttribute("aria-describedby")).toBe(false)
  })

  it("does not turn accessible labels or citation previews into extra tooltips", async () => {
    await render(<button aria-label="Source 1: Robotics paper">1</button>)
    await hover()
    await advance()
    expect(tip()).toBeNull()
    await act(async () => button().focus())
    await advance()
    expect(tip()).toBeNull()
  })

  it("keeps descriptions available on disabled shared buttons", async () => {
    await render(<Button disabled data-tooltip="Describe your research interests to start a run">Start run</Button>)
    await hover()
    await advance()
    expect(tip()?.textContent).toBe("Describe your research interests to start a run")
    expect(button().disabled).toBe(true)
  })

  it("stays open while the pointer enters the tooltip", async () => {
    await render()
    await hover()
    await advance()
    const tooltip = tip()!
    await act(async () => {
      button().dispatchEvent(new MouseEvent("pointerout", { bubbles: true, relatedTarget: tooltip }))
      tooltip.dispatchEvent(new MouseEvent("pointerover", { bubbles: true }))
    })
    await advance(500)
    expect(tip()).toBe(tooltip)
    await act(async () => { tooltip.dispatchEvent(new MouseEvent("pointerout", { bubbles: true })) })
    await advance(120)
    expect(tip()).toBeNull()
  })

  it("cancels a hint when the pointer leaves before the delay", async () => {
    await render()
    await hover()
    await act(async () => { button().dispatchEvent(new MouseEvent("pointerout", { bubbles: true })) })
    await advance()
    expect(tip()).toBeNull()
  })

  it("keeps the opening delay when moving between a button and its icon", async () => {
    await render()
    await hover()
    await advance(200)
    await hover(button().querySelector("span")!)
    await advance(250)
    expect(tip()?.textContent).toBe("Copy the subject and message")
  })

  it("opens on focus even when a hover hint is pending", async () => {
    await render()
    await hover()
    await act(async () => { button().focus() })
    await advance(0)
    expect(tip()?.textContent).toBe("Copy the subject and message")
  })

  it("dismisses on scroll and removes descriptions when controls change", async () => {
    await render()
    await hover()
    await advance()
    await act(async () => { document.dispatchEvent(new Event("scroll")) })
    expect(tip()).toBeNull()
    await hover()
    await advance()
    await render(<Button data-tooltip="Copied successfully">Copy</Button>)
    expect(tip()).toBeNull()
    await hover()
    await advance()
    expect(tip()?.textContent).toBe("Copied successfully")
  })

  it("ignores touch and explicit opt-outs", async () => {
    await render()
    await hover(button(), "touch")
    await advance()
    expect(tip()).toBeNull()
    await render(<button aria-label="Close" data-tooltip="">×</button>)
    await hover()
    await advance()
    expect(tip()).toBeNull()
  })

  it("does not show a sticky hint when tapping a focusable control", async () => {
    await render()
    await act(async () => {
      const event = new MouseEvent("pointerdown", { bubbles: true })
      Object.defineProperty(event, "pointerType", { value: "touch" })
      button().dispatchEvent(event)
      button().focus()
    })
    await advance()
    expect(tip()).toBeNull()
    await act(async () => {
      button().blur()
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" }))
      button().focus()
    })
    await advance(0)
    expect(tip()?.textContent).toBe("Copy the subject and message")
  })

  it("closes on activation without stopping the action", async () => {
    const onClick = vi.fn()
    await render(<Button data-tooltip="Copy email" onClick={onClick}>Copy</Button>)
    await hover()
    await advance()
    await act(async () => {
      button().dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }))
      button().click()
    })
    expect(tip()).toBeNull()
    expect(onClick).toHaveBeenCalledOnce()
  })

  it("supports controls portalled outside the app root and removes stale hints", async () => {
    await act(async () => {
      root.render(<TooltipProvider>{createPortal(<button data-tooltip="Close dialog">×</button>, document.body)}</TooltipProvider>)
    })
    const portalled = document.body.querySelector<HTMLButtonElement>("button")!
    await hover(portalled)
    await advance()
    expect(tip()?.textContent).toBe("Close dialog")
    await render(<></>)
    expect(tip()).toBeNull()
  })

  it("hides a tooltip when its menu opens or description changes", async () => {
    await render(<button data-tooltip="More actions" aria-expanded={false}>…</button>)
    await hover()
    await advance()
    await render(<button data-tooltip="More actions" aria-expanded={true}>…</button>)
    expect(tip()).toBeNull()
    await hover()
    await advance()
    expect(tip()).toBeNull()
  })
})

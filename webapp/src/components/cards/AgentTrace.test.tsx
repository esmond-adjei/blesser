// @vitest-environment jsdom
import { act, useState } from "react"
import { createRoot, type Root } from "react-dom/client"
import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { ToolGroup, ToolRow } from "./AgentTrace"
import { TaskCard } from "./TaskCard"
import type { TaskLogEvent } from "../../lib/types"

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
const event: TaskLogEvent = { turn: 27, tool: "search_web", input: { query: "robotics PhD Ghana" }, ok: true, result_preview: "Found 3 programmes" }

function ExpandableRow() {
  const [open, setOpen] = useState(false)
  return <ToolRow event={event} expanded={open} onToggle={() => setOpen(!open)} />
}

describe("tool log rows", () => {
  let host: HTMLDivElement
  let root: Root
  beforeEach(() => {
    host = document.createElement("div")
    document.body.appendChild(host)
    root = createRoot(host)
  })
  afterEach(async () => {
    await act(async () => { root.unmount() })
    host.remove()
  })

  it("shows a descriptive action and a search icon without a turn counter or raw tool name", async () => {
    await act(async () => { root.render(<ExpandableRow />) })
    expect(host.textContent).toContain("Searched the web")
    expect(host.textContent).not.toContain("27")
    expect(host.querySelector(".lucide-search")).not.toBeNull()
    expect(host.querySelector(".lucide-circle-check")).toBeNull()
    expect(host.textContent).not.toContain("search_web")
  })

  it("uses a focusable disclosure and reveals the parameters and readable result", async () => {
    await act(async () => { root.render(<ExpandableRow />) })
    const button = host.querySelector("button")!
    button.focus()
    expect(document.activeElement).toBe(button)
    expect(button.getAttribute("aria-expanded")).toBe("false")
    await act(async () => { button.click() })
    expect(button.getAttribute("aria-expanded")).toBe("true")
    expect(host.textContent).toContain("Searched the web")
    expect(host.textContent).not.toContain("search_web")
    expect(host.querySelectorAll("pre")[0].textContent).toContain('"query": "robotics PhD Ghana"')
    expect(host.textContent).toContain("Found 3 programmes")
    await act(async () => { button.click() })
    expect(host.querySelector("pre")).toBeNull()
  })

  it("keeps running and failed states distinct", async () => {
    await act(async () => { root.render(<ToolRow event={{ ...event, ok: undefined }} expanded={false} onToggle={() => {}} />) })
    expect(host.textContent).toContain("Running: Searching the web")
    expect(host.querySelector(".animate-spin")).not.toBeNull()
    await act(async () => { root.render(<ToolRow event={{ ...event, ok: false }} expanded={false} onToggle={() => {}} />) })
    expect(host.textContent).toContain("Failed: Searching the web")
    expect(host.querySelector(".text-destructive")).not.toBeNull()
    expect(host.querySelector(".animate-spin")).toBeNull()
  })

  it("summarizes a completed group using its final action and matching icon", async () => {
    await act(async () => {
      root.render(<ToolGroup events={[event, { ...event, tool: "save_program", input: { program_name: "Computer Science", school_name: "University of Ghana" } }]} defaultOpen={false} />)
    })
    expect(host.textContent).toContain("Saved programme")
    expect(host.textContent).toContain("2 actions")
    expect(host.querySelector(".lucide-graduation-cap")).not.toBeNull()
    expect(host.textContent).not.toContain("tool calls")
  })

  it("removes turn counts from task stats while preserving usage and elapsed time", () => {
    const html = renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <TaskCard runId="r1" task={{ id: "t1", task_type: "research_one_professor", target_name: "Ada Lovelace", turns: 27, status: "done", error: null, input_tokens: 120, output_tokens: 30, duration_seconds: 65, log: [] }} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(html).not.toMatch(/27 turns|turn 27/)
    expect(html).toContain("150 tok")
    expect(html).toContain("1m 5s")
  })

  it("shows one saved application card for successful saves", () => {
    const save: TaskLogEvent = { turn: 1, tool: "save_application", ok: true, input: { school: "MIT", program: "PhD in CS" }, result_preview: '{"application_id":"a1","created":true}' }
    const html = renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <TaskCard runId="r1" task={{ id: "t1", task_type: "research_one_professor", target_name: "Ada", turns: 1, status: "done", error: null, log: [save, save, { ...save, ok: false, result_preview: '{"application_id":"a2"}' }] }} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(html.match(/Open PhD in CS in the detail panel/g)).toHaveLength(1)
    expect(html).toContain("MIT")
  })
})

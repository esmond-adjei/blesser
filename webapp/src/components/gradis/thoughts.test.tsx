// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { GradisProvider, useGradis } from "./GradisProvider"
import { AgentTrace, traceSegments } from "../cards/AgentTrace"
import { streamChat, type GradisEvent } from "../../lib/gradis"

vi.mock("../../lib/providers", async importOriginal => ({
  ...await importOriginal<typeof import("../../lib/providers")>(),
  useDefaultModel: () => "system",
  useProviderConfigs: () => ({ configs: [], isLoading: false, isError: false }),
}))
// The lazy renderer would show its loading skeleton for the whole test.
vi.mock("../ui/MarkdownLazy", () => ({ Markdown: ({ text }: { text: string }) => <div>{text}</div> }))
vi.mock("../../lib/gradis", async importOriginal => ({
  ...await importOriginal<typeof import("../../lib/gradis")>(),
  listConversations: vi.fn(async () => []),
  createConversation: vi.fn(async () => ({ id: "chat-1", title: "Test", has_pending: false })),
  getConversation: vi.fn(async () => ({ id: "chat-1", title: "Test", messages: [], pending_call: null, queue: [] })),
  streamChat: vi.fn(async () => {}),
}))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
let host: HTMLDivElement
let root: Root
let emit: (event: GradisEvent) => void = () => {}

function Probe() {
  const gradis = useGradis()
  return <>
    <button onClick={() => void gradis.send("Tighten it")}>Send</button>
    {gradis.draft && <AgentTrace events={gradis.draft.segments ?? []} working />}
  </>
}

beforeEach(async () => {
  localStorage.clear()
  vi.mocked(streamChat).mockImplementation(async (_id, _text, _context, onEvent) => {
    emit = (event) => onEvent(event)
    await new Promise(() => {})
  })
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root.render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><GradisProvider><Probe /></GradisProvider></MemoryRouter></QueryClientProvider>) })
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

it("shows the model's thoughts as they stream, then folds them when it answers", async () => {
  await act(async () => host.querySelector("button")!.click())
  await act(async () => emit({ type: "reasoning", text: "A first try" }))
  await act(async () => emit({ type: "reasoning", text: "", reset: true }))
  await act(async () => emit({ type: "reasoning", text: "Shorten the summary." }))
  const toggle = [...host.querySelectorAll("button")].find((b) => b.textContent === "Thinking")!
  expect(toggle.getAttribute("aria-expanded")).toBe("true")
  expect(host.textContent).toContain("Shorten the summary.")
  expect(host.textContent).not.toContain("A first try")
  await act(async () => emit({ type: "token", text: "Here it is." }))
  const folded = [...host.querySelectorAll("button")].find((b) => b.textContent === "Thoughts")!
  expect(folded.getAttribute("aria-expanded")).toBe("false")
  expect(host.textContent).not.toContain("Shorten the summary.")
  await act(async () => folded.click())
  expect(host.textContent).toContain("Shorten the summary.")
})

it("puts a turn's thoughts before what it said", () => {
  const parts = traceSegments([{ kind: "turn", turn: 1, note: "Done.", thought: "Weighing it." }])
  expect(parts.map((p) => p.kind)).toEqual(["thought", "note"])
  expect(traceSegments([{ kind: "turn", turn: 1, note: "Done." }]).map((p) => p.kind)).toEqual(["note"])
})

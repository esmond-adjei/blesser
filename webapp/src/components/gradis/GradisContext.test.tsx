// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { GradisProvider, useGradis } from "./GradisProvider"
import { useAutoPageContext } from "../../lib/chatPreferences"
import { streamChat } from "../../lib/gradis"

vi.mock("../../lib/providers", async importOriginal => ({
  ...await importOriginal<typeof import("../../lib/providers")>(),
  useDefaultModel: () => "system",
  useProviderConfigs: () => ({ configs: [], isLoading: false, isError: false }),
}))
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
function Probe() {
  const [auto, setAuto] = useAutoPageContext()
  const gradis = useGradis()
  return <>
    <button onClick={() => setAuto(!auto)}>Toggle auto context</button>
    <button onClick={() => gradis.attachSelection("Selected research paragraph")}>Attach selection</button>
    <button onClick={() => gradis.setEffort("xhigh")}>Use extra high effort</button>
    <button onClick={() => gradis.setAttachments([{ kind: "text", name: "paper.txt", text: "Research summary" }])}>Attach paper</button>
    <button onClick={() => void gradis.send("Explain this")}>Send</button>
    <output>{gradis.contextChips.map(chip => chip.key).join(",")}</output>
    <aside data-context-source><p id="research-detail">Faculty research on soft robotics</p></aside>
  </>
}
async function renderAt(path: string) {
  host = document.createElement("div")
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => { root.render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><GradisProvider><Probe /></GradisProvider></MemoryRouter></QueryClientProvider>) })
}

async function selectResearchDetail() {
  const text = host.querySelector("#research-detail")?.firstChild
  expect(text).toBeTruthy()
  const range = document.createRange()
  range.selectNodeContents(text!)
  Object.defineProperty(range, "getBoundingClientRect", {
    value: () => ({ left: 20, bottom: 40 }),
  })
  window.getSelection()?.removeAllRanges()
  window.getSelection()?.addRange(range)
  await act(async () => document.dispatchEvent(new Event("pointerup")))
}

function findPopup() {
  return [...document.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent?.includes("Add to Gradis context"))
}

beforeEach(async () => {
  localStorage.clear()
  vi.clearAllMocks()
  await renderAt("/schools/school-1")
})
afterEach(async () => { await act(async () => root.unmount()); window.getSelection()?.removeAllRanges(); host.remove() })

it("adds page context only when switched on and still sends explicitly selected text", async () => {
  // Off by default: the page is a suggestion until added.
  expect(host.querySelector("output")?.textContent).toBe("")
  const buttons = host.querySelectorAll("button")
  await act(async () => buttons[0].click())
  expect(host.querySelector("output")?.textContent).toBe("page")
  await act(async () => buttons[0].click())
  expect(host.querySelector("output")?.textContent).toBe("")
  await act(async () => buttons[1].click())
  expect(host.querySelector("output")?.textContent).toBe("selection")
  await act(async () => buttons[4].click())
  expect(streamChat).toHaveBeenCalledOnce()
  expect(vi.mocked(streamChat).mock.calls[0][2]).toEqual({
    page: "", run_id: null, candidate_id: null, application_id: null, draft_id: null,
    document_id: null, cv_version_id: null, selection: "Selected research paragraph", attachments: [],
    // Only the chip still on: the bubble shows what the prompt was sent with.
    chips: [{ key: "selection", label: "Selection", detail: "Selected research paragraph" }],
  })
})

it("sends the selected effort and attachment with the next message", async () => {
  const buttons = host.querySelectorAll("button")
  await act(async () => buttons[2].click())
  await act(async () => buttons[3].click())
  await act(async () => buttons[4].click())
  const call = vi.mocked(streamChat).mock.calls[0]
  expect(call[2].attachments).toEqual([{ kind: "text", name: "paper.txt", text: "Research summary" }])
  expect(call[5]).toEqual({ provider: "system", effort: "xhigh" })
})

it("offers selected text in a detail panel and attaches it to the next prompt", async () => {
  await selectResearchDetail()
  const popup = findPopup()
  expect(popup).toBeTruthy()
  await act(async () => popup!.click())
  expect(host.querySelector("output")?.textContent).toBe("selection")
  await act(async () => [...host.querySelectorAll("button")].find(button => button.textContent === "Send")?.click())
  expect(vi.mocked(streamChat).mock.calls[0][2].selection).toBe("Faculty research on soft robotics")
})

it("stays hidden on listing pages", async () => {
  await act(async () => root.unmount())
  host.remove()
  await renderAt("/schools")
  await selectResearchDetail()
  expect(findPopup()).toBeUndefined()
})

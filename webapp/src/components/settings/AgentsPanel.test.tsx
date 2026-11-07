// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { AgentTool } from "../../lib/types"
import { AgentsPanel } from "./AgentsPanel"

const mutations = vi.hoisted(() => ({ tool: vi.fn(), task: vi.fn(), group: vi.fn() }))
const tools: AgentTool[] = [
  { name: "search_web", scope: "worker", enabled: true, read_only: true, confirm_required: false, description: "Search public pages.", group: null, updated_at: null },
  { name: "fetch_page", scope: "worker", enabled: true, read_only: true, confirm_required: false, description: "Read a public page.", group: null, updated_at: null },
  { name: "delete_run", scope: "assistant", enabled: true, read_only: false, confirm_required: true, description: "Remove a saved run.", group: null, updated_at: null },
]
vi.mock("../../lib/agents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/agents")>()
  return {
    ...actual,
    useAgentTools: () => ({ tools, groups: [], isLoading: false, isError: false, update: mutations.tool, updateGroup: mutations.group }),
    useAgentTasks: () => ({ tasks: [{ task_type: "discover_programs", enabled: true, tools: ["search_web"], updated_at: null }], isLoading: false, isError: false, update: mutations.task }),
  }
})
vi.mock("../../lib/toast", () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }))
const auth = vi.hoisted(() => ({ updateUser: vi.fn(), setAgentFullAccess: vi.fn(async (on: boolean) => ({ agent_full_access: on })) }))
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ user: { agent_full_access: false }, updateUser: auth.updateUser }) }))
vi.mock("../../lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../../lib/api")>()), setAgentFullAccess: auth.setAgentFullAccess }))
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

describe("agent settings", () => {
  let host: HTMLDivElement
  let root: Root
  function button(label: string) {
    const found = Array.from(host.querySelectorAll("button")).find((element) => element.textContent?.includes(label) || element.getAttribute("aria-label") === label)
    if (!found) throw new Error(`Button not found: ${label}`)
    return found
  }
  beforeEach(async () => {
    vi.clearAllMocks()
    host = document.createElement("div")
    document.body.append(host)
    root = createRoot(host)
    await act(async () => { root.render(<AgentsPanel />) })
  })
  afterEach(async () => {
    await act(async () => { root.unmount() })
    host.remove()
  })

  it("keeps the last allowed tool selected and restores defaults explicitly", async () => {
    await act(async () => { button("Discover programmes").click() })
    const allowed = host.querySelector('button[aria-pressed="true"][data-tooltip="Keep one selected, or switch this activity off"]')
    expect(allowed?.hasAttribute("disabled")).toBe(true)
    expect(host.innerHTML).not.toMatch(/search_web|fetch_page|discover_programs/)
    expect(host.textContent).not.toContain("read only")
    await act(async () => { button("Restore defaults").click() })
    expect(mutations.task).toHaveBeenCalledWith("discover_programs", { tools: [] })
  })

  it("lets Gradis changes ask first, tool by tool", async () => {
    await act(async () => { button("Gradis").click() })
    expect(host.textContent).toContain("Delete a research run")
    expect(host.textContent).not.toContain("Research activities")
    const ask = host.querySelector('input[aria-label="Ask before Delete a research run"]')
    if (!(ask instanceof HTMLInputElement)) throw new Error("Ask first checkbox not found")
    await act(async () => { ask.click() })
    expect(mutations.tool).toHaveBeenCalledWith("assistant", "delete_run", { confirm_required: false })
  })

  it("gives Gradis full access in one choice", async () => {
    await act(async () => { button("Gradis").click() })
    await act(async () => { button("Full access").click() })
    expect(auth.setAgentFullAccess).toHaveBeenCalledWith(true)
    expect(auth.updateUser).toHaveBeenCalledWith({ agent_full_access: true })
  })
})

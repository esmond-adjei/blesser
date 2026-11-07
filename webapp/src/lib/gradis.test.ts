// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { loadAgentMode, storeAgentMode, streamChat, streamConfirm } from "./gradis"

/** A fetch that records request bodies and answers with an empty stream. */
function captureFetch() {
  const bodies: Record<string, unknown>[] = []
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)))
    return new Response(new ReadableStream({ start: (c) => c.close() }), { status: 200 })
  })
  vi.stubGlobal("fetch", fetchMock)
  return bodies
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe("agent mode", () => {
  it("defaults to agent and persists across a reload", () => {
    expect(loadAgentMode()).toBe("agent")
    storeAgentMode("chat")
    // A reload reads it back from storage.
    expect(loadAgentMode()).toBe("chat")
    localStorage.setItem("gradis.agent_mode", "godmode")
    expect(loadAgentMode()).toBe("agent")
  })

  it.each([["ask", "chat"], ["assist", "agent"]])("migrates the saved %s preference to %s", (oldMode, newMode) => {
    localStorage.setItem("gradis.agent_mode", oldMode)
    expect(loadAgentMode()).toBe(newMode)
    expect(localStorage.getItem("gradis.agent_mode")).toBe(newMode)
  })

  it("rides along with every turn and approval", async () => {
    const bodies = captureFetch()
    await streamChat("c1", "hi", { page: "/" }, () => {}, undefined, null, { mode: "chat" })
    await streamChat("c1", "hi", { page: "/" }, () => {})
    await streamConfirm("c1", "call1", true, { page: "/" }, () => {}, undefined, null, "agent")
    expect(bodies.map((b) => b.mode)).toEqual(["chat", "agent", "agent"])
  })
})

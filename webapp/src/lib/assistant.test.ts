import { afterEach, expect, it, vi } from "vitest"
import { activitySummary, streamTurn, type AssistantEvent, type TraceEntry } from "./assistant"
import { setAccessToken, setRefreshHandler } from "./api"

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
  setRefreshHandler(null)
})

function response(chunks: string[]) {
  const encoder = new TextEncoder()
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  }))
}

it("reads split SSE frames and ignores heartbeat comments", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([
    ": keep-alive\n\nevent: status\nda",
    'ta: {"message":"Checking"}\n\nevent: commentary\nda',
    'ta: {"text":"I\'ll check the catalog."}\n\nevent: to',
    'ken\ndata: {"text":"Here is what I found."}\n\nevent: done\ndata: {}\n\n',
  ])))
  const events: AssistantEvent[] = []
  await streamTurn("chat-1", { type: "live" }, (event) => events.push(event), new AbortController().signal)
  expect(events).toEqual([
    { type: "status", message: "Checking" },
    { type: "commentary", text: "I'll check the catalog." },
    { type: "token", text: "Here is what I found." },
    { type: "done" },
  ])
})

it("summarises grouped activity and ignores commentary", () => {
  const entries: TraceEntry[] = [
    { kind: "commentary", text: "I'll check a few things." },
    { tool: "search_catalog", label: "Searched the Blesser catalog, 2 matches", ok: true, note: "" },
    { tool: "list_todos", label: "Checked your to-dos, 3 matches", ok: true, note: "" },
    { kind: "commentary", text: "Now your applications." },
    { tool: "list_applications", label: "Checked your applications", ok: false, note: "" },
  ]
  expect(activitySummary(entries)).toBe(
    "Searched the catalog, checked your to-dos, and tried to check your applications",
  )
  expect(activitySummary([entries[3]])).toBe("")
})

it("refreshes a rejected token before opening the authenticated chat stream", async () => {
  setAccessToken("expired")
  setRefreshHandler(async () => "fresh")
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(null, { status: 401 }))
    .mockResolvedValueOnce(response(["event: done\ndata: {}\n\n"]))
  vi.stubGlobal("fetch", fetch)
  await streamTurn("chat-1", { type: "chat", content: "What's open?" }, () => {}, new AbortController().signal)
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe("Bearer expired")
  expect(fetch.mock.calls[1][1]).toMatchObject({
    method: "POST", headers: { Authorization: "Bearer fresh" }, body: JSON.stringify({ content: "What's open?" }),
  })
})

it("reports an interrupted turn without a terminal frame", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(['event: status\ndata: {"message":"Checking"}\n\n'])))
  await expect(streamTurn("chat-1", { type: "live" }, () => {}, new AbortController().signal))
    .rejects.toThrow("The reply stream was interrupted.")
})

it("counts thoughts as thinking, not as tool steps", () => {
  const entries: TraceEntry[] = [
    { kind: "thought", text: "Check the catalog first." },
    { kind: "tool", tool: "search_catalog", label: "Searched", ok: true, note: "" },
  ]
  expect(activitySummary(entries)).toBe("Thought it through and searched the catalog")
  expect(activitySummary([entries[0]])).toBe("Thought it through")
})

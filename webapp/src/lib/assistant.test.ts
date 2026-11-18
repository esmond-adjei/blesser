import { afterEach, expect, it, vi } from "vitest"
import { streamTurn, type AssistantEvent } from "./assistant"
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
    'ta: {"message":"Checking"}\n\nevent: to',
    'ken\ndata: {"text":"Here is what I found."}\n\nevent: done\ndata: {}\n\n',
  ])))
  const events: AssistantEvent[] = []
  await streamTurn("chat-1", { type: "live" }, (event) => events.push(event), new AbortController().signal)
  expect(events).toEqual([
    { type: "status", message: "Checking" },
    { type: "token", text: "Here is what I found." },
    { type: "done" },
  ])
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

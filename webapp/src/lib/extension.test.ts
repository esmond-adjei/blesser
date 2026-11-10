import { afterEach, describe, expect, it, vi } from "vitest"
import { browserName, handToExtension, parseConnectParams } from "./extension"

const EXT = "abcdefghijklmnopabcdefghijklmnop"
const STATE = "Zm9vYmFyYmF6cXV4MTIzNDU2"
const grant = { access_token: "a", refresh_token: "r", session: { id: "s", name: "Chrome on Linux", created_at: "", last_used_at: null } }

afterEach(() => {
  delete (globalThis as { chrome?: unknown }).chrome
})

describe("parseConnectParams", () => {
  it("accepts a real extension id and state and rejects anything else", () => {
    expect(parseConnectParams(new URLSearchParams({ ext: EXT, state: STATE }))).toEqual({ ext: EXT, state: STATE })
    expect(parseConnectParams(new URLSearchParams({ ext: "zzz", state: STATE }))).toBeNull()
    expect(parseConnectParams(new URLSearchParams({ ext: EXT, state: "short" }))).toBeNull()
    expect(parseConnectParams(new URLSearchParams({ ext: EXT }))).toBeNull()
  })
})

describe("browserName", () => {
  it("names the browser and system", () => {
    expect(browserName("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/142.0 Safari/537.36")).toBe("Chrome on Linux")
    expect(browserName("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/142.0 Safari/537.36 Edg/142.0")).toBe("Edge on Windows")
    expect(browserName("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Chrome/142.0")).toBe("Chrome on macOS")
  })
})

describe("handToExtension", () => {
  it("reports an unreachable extension when chrome.runtime is missing", async () => {
    expect(await handToExtension({ ext: EXT, state: STATE }, grant)).toEqual({ ok: false, reason: "unreachable" })
  })

  it("sends the tokens with the state and relays the extension's verdict", async () => {
    const sendMessage = vi.fn((_id: string, _msg: unknown, cb: (r: unknown) => void) => cb({ ok: false, error: "state_mismatch" }))
    ;(globalThis as { chrome?: unknown }).chrome = { runtime: { sendMessage } }
    expect(await handToExtension({ ext: EXT, state: STATE }, grant)).toEqual({ ok: false, reason: "state_mismatch" })
    expect(sendMessage).toHaveBeenCalledWith(EXT, { type: "blesser.connect", state: STATE, ...grant }, expect.any(Function))
  })
})

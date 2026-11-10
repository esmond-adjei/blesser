import type { ExtensionGrant } from "./api"

export interface ConnectParams {
  ext: string
  state: string
}

/** Chrome and Edge extension ids are 32 letters a to p; the state is the extension's random nonce. */
export function parseConnectParams(params: URLSearchParams): ConnectParams | null {
  const ext = params.get("ext") ?? ""
  const state = params.get("state") ?? ""
  if (!/^[a-p]{32}$/.test(ext) || !/^[A-Za-z0-9_-]{16,128}$/.test(state)) return null
  return { ext, state }
}

export function browserName(ua: string, platform = ""): string {
  const browser = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Brave/.test(ua) ? "Brave" : /Chrome\//.test(ua) ? "Chrome" : "Browser"
  const os = /Windows/.test(ua) ? "Windows" : /CrOS/.test(ua) ? "ChromeOS" : /Mac OS X/.test(ua) ? "macOS" : /Android/.test(ua) ? "Android" : /Linux/.test(ua || platform) ? "Linux" : ""
  return os ? `${browser} on ${os}` : browser
}

interface ChromeRuntime {
  sendMessage(id: string, message: unknown, callback: (reply: unknown) => void): void
  lastError?: { message?: string }
}

export type HandoffResult = { ok: true } | { ok: false; reason: "unreachable" | "state_mismatch" | "rejected" }

/** Hands the new tokens to the extension; only pages listed in its externally_connectable can reach it. */
export function handToExtension(params: ConnectParams, grant: ExtensionGrant): Promise<HandoffResult> {
  const runtime = (globalThis as { chrome?: { runtime?: ChromeRuntime } }).chrome?.runtime
  if (!runtime?.sendMessage) return Promise.resolve({ ok: false, reason: "unreachable" })
  return new Promise((resolve) => {
    try {
      runtime.sendMessage(params.ext, { type: "blesser.connect", state: params.state, ...grant }, (reply) => {
        const error = runtime.lastError
        const answer = reply as { ok?: boolean; error?: string } | undefined
        if (error || !answer) resolve({ ok: false, reason: "unreachable" })
        else if (answer.ok) resolve({ ok: true })
        else resolve({ ok: false, reason: answer.error === "state_mismatch" ? "state_mismatch" : "rejected" })
      })
    } catch {
      resolve({ ok: false, reason: "unreachable" })
    }
  })
}

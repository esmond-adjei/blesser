import type { ConnectPayload } from "../shared/types"
import type { Store } from "./store"

export function newState(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(24))
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

export function connectUrl(appUrl: string, extensionId: string, state: string): string {
  const url = new URL("/connect/extension", appUrl)
  url.searchParams.set("ext", extensionId)
  url.searchParams.set("state", state)
  return url.toString()
}

function isPayload(message: unknown): message is ConnectPayload {
  const m = message as Partial<ConnectPayload> | null
  return (
    !!m && m.type === "blesser.connect" && typeof m.state === "string" && typeof m.access_token === "string" &&
    typeof m.refresh_token === "string" && !!m.session && typeof m.session.id === "string"
  )
}

/** Accepts tokens only from the configured app origin and only for the state this extension issued. */
export async function acceptConnect(store: Store, message: unknown, senderUrl: string | undefined): Promise<{ ok: boolean; error?: string }> {
  if (!isPayload(message)) return { ok: false, error: "bad_message" }
  const { appUrl } = await store.settings()
  let origin = ""
  try {
    origin = new URL(senderUrl ?? "").origin
  } catch {
    return { ok: false, error: "bad_origin" }
  }
  if (origin !== new URL(appUrl).origin) return { ok: false, error: "bad_origin" }
  if (!(await store.takeConnect(message.state))) return { ok: false, error: "state_mismatch" }
  await store.saveAuth({ access_token: message.access_token, refresh_token: message.refresh_token, session_id: message.session.id })
  return { ok: true }
}

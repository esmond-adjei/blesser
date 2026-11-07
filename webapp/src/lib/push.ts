/**
 * Never ask permission on page load; callers ask at a moment that explains itself.
 * iOS push works only for Home Screen sites (16.4+), so `pushSupport` reports that.
 */
import * as api from "./api"

const SW_URL = "/sw.js"

export type PushSupport = "supported" | "unsupported" | "ios-needs-home-screen"

function isIos(): boolean {
  const ua = navigator.userAgent
  // iPadOS reports itself as a Mac with touch.
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1)
}

function isStandalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}

export function pushSupport(): PushSupport {
  if (typeof window === "undefined") return "unsupported"
  const capable = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window
  if (isIos() && !isStandalone()) return "ios-needs-home-screen"
  return capable ? "supported" : "unsupported"
}

export function permission(): NotificationPermission | "unsupported" {
  return typeof Notification === "undefined" ? "unsupported" : Notification.permission
}

export function browserTimezone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
  } catch {
    return undefined
  }
}

async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null
  const existing = await navigator.serviceWorker.getRegistration(SW_URL)
  return existing ?? navigator.serviceWorker.register(SW_URL)
}

/** This browser's subscription, if it has one (no prompt, no register). */
export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!("serviceWorker" in navigator)) return null
  try {
    const reg = await navigator.serviceWorker.getRegistration(SW_URL)
    return (await reg?.pushManager.getSubscription()) ?? null
  } catch {
    return null
  }
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "===".slice((base64url.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/")
  const raw = atob(padded)
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

/**
 * Ask for permission (if needed), subscribe, and save the subscription.
 * Must run from a user gesture. Resolves to why it didn't work, or "ok".
 */
export async function enablePush(): Promise<"ok" | "denied" | "unavailable" | "server-off"> {
  if (pushSupport() !== "supported") return "unavailable"
  const config = await api.getPushConfig()
  if (!config.enabled || !config.public_key) return "server-off"
  const granted = await Notification.requestPermission()
  if (granted !== "granted") return "denied"
  const reg = await registration()
  if (!reg) return "unavailable"
  await navigator.serviceWorker.ready
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(config.public_key) }))
  const json = sub.toJSON()
  await api.savePushSubscription({
    endpoint: sub.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
    timezone: browserTimezone(),
  })
  return "ok"
}

/** Remove this browser's subscription here and on the server. */
export async function disablePush(): Promise<void> {
  const sub = await currentSubscription()
  if (!sub) return
  try {
    await api.removePushSubscription(sub.endpoint)
  } finally {
    await sub.unsubscribe().catch(() => false)
  }
}

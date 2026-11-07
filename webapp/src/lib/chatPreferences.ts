import * as React from "react"

const KEY = "graduator.chat.autoContext"
const EVENT = "graduator:chat-preferences"
// Off by default: page chips are suggestions until clicked.
let fallback = false
function snapshot() {
  try { return localStorage.getItem(KEY) === "on" } catch { return fallback }
}
function subscribe(notify: () => void) {
  window.addEventListener(EVENT, notify)
  window.addEventListener("storage", notify)
  return () => { window.removeEventListener(EVENT, notify); window.removeEventListener("storage", notify) }
}
export function useAutoPageContext() {
  const enabled = React.useSyncExternalStore(subscribe, snapshot, () => false)
  function setEnabled(value: boolean) {
    fallback = value
    try { localStorage.setItem(KEY, value ? "on" : "off") } catch { /* session preference */ }
    window.dispatchEvent(new Event(EVENT))
  }
  return [enabled, setEnabled] as const
}

import type { PanelMessage, Reply } from "./types"

export async function send<T>(message: PanelMessage): Promise<T> {
  const reply = (await chrome.runtime.sendMessage(message)) as Reply<T> | undefined
  if (!reply) throw new Error("The Blesser extension didn't answer. Try again.")
  if (!reply.ok) throw new Error(reply.error)
  return reply.data
}

/** Follows the OS theme, like the member app's "System" mode. */
export function followTheme() {
  const media = window.matchMedia("(prefers-color-scheme: dark)")
  const apply = () => (document.documentElement.dataset.theme = media.matches ? "dark" : "light")
  media.addEventListener("change", apply)
  apply()
}

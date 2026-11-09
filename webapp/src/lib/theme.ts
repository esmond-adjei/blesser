import * as React from "react"
import { Monitor, Moon, Sun } from "lucide-react"

export type ThemeMode = "system" | "light" | "dark"
export type ResolvedTheme = "light" | "dark"

/** Read by the inline script in index.html too; keep the two in step. */
export const THEME_KEY = "blesser.theme"

export const THEME_MODES: { value: ThemeMode; label: string; Icon: typeof Sun }[] = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
]

export function parseTheme(raw: unknown): ThemeMode {
  return raw === "light" || raw === "dark" ? raw : "system"
}

export function resolveTheme(mode: ThemeMode, systemDark: boolean): ResolvedTheme {
  return mode === "system" ? (systemDark ? "dark" : "light") : mode
}

function readStored(): ThemeMode {
  try {
    return parseTheme(localStorage.getItem(THEME_KEY))
  } catch {
    return "system"
  }
}

const listeners = new Set<() => void>()
let mode: ThemeMode | null = null
let media: MediaQueryList | null = null

function current(): ThemeMode {
  return (mode ??= readStored())
}

function apply() {
  document.documentElement.dataset.theme = resolveTheme(current(), media?.matches ?? false)
}

function emit() {
  apply()
  listeners.forEach((fn) => fn())
}

/** Applies the stored theme and follows the OS (for "system") and other tabs. */
export function initTheme() {
  if (media) return
  media = window.matchMedia("(prefers-color-scheme: dark)")
  media.addEventListener("change", emit)
  window.addEventListener("storage", (e) => {
    if (e.key !== THEME_KEY) return
    mode = parseTheme(e.newValue)
    emit()
  })
  apply()
}

export function setTheme(next: ThemeMode) {
  try {
    localStorage.setItem(THEME_KEY, next)
  } catch {
    /* storage blocked: the choice lasts for this page */
  }
  mode = next
  emit()
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => void listeners.delete(fn)
}

export function useTheme() {
  const value = React.useSyncExternalStore(subscribe, current, () => "system" as ThemeMode)
  const systemDark = React.useSyncExternalStore(subscribe, () => media?.matches ?? false, () => false)
  return { mode: value, resolved: resolveTheme(value, systemDark), setTheme }
}

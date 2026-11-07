import { Monitor, Moon, Sun } from "lucide-react"
import * as React from "react"

/** Theme preference, persisted locally and applied as `.dark` on <html>.
 * "system" follows the OS and reacts to live OS changes. */
export type ThemeMode = "light" | "dark" | "system"
export type ResolvedTheme = "light" | "dark"

const STORAGE_KEY = "graduator.theme"

export const THEME_OPTIONS: { value: ThemeMode; label: string; Icon: typeof Sun }[] = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
]

function resolveSystem(): ResolvedTheme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function getTheme(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === "light" || v === "dark" || v === "system" ? v : "system"
  } catch {
    return "system"
  }
}

function applyTheme(mode: ResolvedTheme) {
  document.documentElement.classList.toggle("dark", mode === "dark")
}

export function useTheme() {
  const [mode, setModeState] = React.useState<ThemeMode>(getTheme)
  const [systemDark, setSystemDark] = React.useState<boolean>(() => resolveSystem() === "dark")

  React.useEffect(() => {
    if (mode !== "system") return
    setSystemDark(resolveSystem() === "dark")
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [mode])

  const resolved: ResolvedTheme = mode === "system" ? (systemDark ? "dark" : "light") : mode

  React.useEffect(() => {
    applyTheme(resolved)
  }, [resolved])

  const setTheme = React.useCallback((next: ThemeMode) => {
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* private mode — theme still applies for the session */
    }
    setModeState(next)
  }, [])

  return { mode, resolved, setTheme }
}

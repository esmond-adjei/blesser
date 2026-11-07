/** Kept out of MarkdownEditor so the toolbar doesn't pull CodeMirror into the page's first chunk. */
export const SHORTCUTS = {
  bold: "Mod-b",
  italic: "Mod-i",
  underline: "Mod-u",
  link: "Mod-k",
  suggest: "Mod-j",
  bullets: "Mod-Shift-8",
  numbers: "Mod-Shift-7",
  normal: "Mod-Alt-0",
  h1: "Mod-Alt-1",
  h2: "Mod-Alt-2",
  h3: "Mod-Alt-3",
  undo: "Mod-z",
  redo: "Mod-Shift-z",
  find: "Mod-f",
  save: "Mod-s",
  commands: "Mod-/",
} as const

const MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)

/** "Mod-Shift-8" as people read it: "⌘⇧8" on a Mac, "Ctrl+Shift+8" elsewhere. */
export function shortcutLabel(key: string): string {
  const parts = key.split("-")
  const last = parts.pop() ?? ""
  const name = last.length === 1 ? last.toUpperCase() : last
  if (MAC) {
    const sym: Record<string, string> = { Mod: "⌘", Shift: "⇧", Alt: "⌥", Ctrl: "⌃" }
    return parts.map((p) => sym[p] ?? p).join("") + name
  }
  return [...parts.map((p) => (p === "Mod" ? "Ctrl" : p)), name].join("+")
}

/** "Bold (Ctrl+B)": a control's tooltip with its shortcut. */
export const withShortcut = (label: string, key: keyof typeof SHORTCUTS) => `${label} (${shortcutLabel(SHORTCUTS[key])})`

import type { CvSuggestAction } from "../../lib/types"
import { isDelimiterRow, splitRow } from "./editor/tableSyntax"

export type OutlineItem = { level: number; text: string; pos: number }

/** The one change turning `a` into `b`, so an applied suggestion edits only its range and the cursor, undo and marks stay put. */
export function minimalChange(a: string, b: string): { from: number; to: number; insert: string } | null {
  if (a === b) return null
  const max = Math.min(a.length, b.length)
  let start = 0
  while (start < max && a.charCodeAt(start) === b.charCodeAt(start)) start++
  let end = 0
  while (end < max - start && a.charCodeAt(a.length - 1 - end) === b.charCodeAt(b.length - 1 - end)) end++
  return { from: start, to: a.length - end, insert: b.slice(start, b.length - end) }
}

/** The most a suggestion can quote (the server's limit). */
export const MAX_SELECTION_CHARS = 8000

export const ACTION_LABEL: Record<CvSuggestAction, string> = {
  improve: "Improve",
  shorten: "Shorten",
  quantify: "Quantify",
  tailor: "Tailor",
  custom: "Change",
}

export function outline(markdown: string): OutlineItem[] {
  const items: OutlineItem[] = []
  let pos = 0
  for (const line of markdown.split("\n")) {
    const m = /^(#{1,6})\s+(.*)$/.exec(line)
    if (m && m[2].trim()) items.push({ level: m[1].length, text: m[2].trim(), pos })
    pos += line.length + 1
  }
  return items
}

/** Copy-as-text mirrors the server's to_plain_text (api/cv/markdown.py), matching the .txt download. */
export function toPlainText(markdown: string): string {
  const lines = markdown.split("\n").flatMap((raw) => {
    // A table's rows: cells apart by tabs, no delimiter row.
    if (/^\s*\|.*\|\s*$/.test(raw)) {
      if (isDelimiterRow(raw)) return []
      raw = splitRow(raw).join("\t")
    }
    let line = raw.replace(/\s+$/, "")
    line = line.replace(/^#{1,6}\s+/, "")
    line = line.replace(/^(\s*)[-*+]\s+/, "$1• ")
    line = line.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label: string, url: string) =>
      label === url ? label : `${label} (${url})`,
    )
    line = line.replace(/(\*\*|__|\*|_|`)(?=\S)(.+?)(?<=\S)\1/g, "$2")
    line = line.replace(/<\/?u>/g, "")
    return line.replace(/\\/g, "")
  })
  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim() + "\n"
}

export function wordCount(markdown: string): number {
  return toPlainText(markdown).split(/\s+/).filter((w) => /\w/.test(w)).length
}

/** A bare address or domain as a link: mail for an email address. */
export function normalizeUrl(raw: string): string {
  const clean = raw.trim()
  if (/^[a-z][a-z0-9+.-]*:/i.test(clean)) return clean
  if (clean.includes("@") && !clean.includes("/")) return `mailto:${clean}`
  return `https://${clean}`
}

export function looksLikeUrl(text: string): boolean {
  const t = text.trim()
  return /^(https?:\/\/|mailto:|www\.)\S+$/i.test(t) || /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(t)
}

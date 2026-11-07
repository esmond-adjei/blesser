/**
 * The editor's copy on this device: edits land here first and reach the server in the
 * background (useDocumentSync), so nothing typed is lost; drafts live only here.
 * Every access tolerates storage being full, blocked or absent.
 */

// From when documents were CVs; renaming it would lose work kept on devices.
const PREFIX = "graduator.cv."

/** A saved CV's (base or variant) text not yet confirmed by the server. */
export type LocalCopy = {
  markdown: string
  title?: string
  baseRevision: number
  /** hashText of the server text at baseRevision: a newer revision with
   * the same text (a rename elsewhere) is not a conflict. */
  baseHash: string
  updatedAt: number
}

/** A tailored variant that exists only on this device. */
export type DocumentDraft = {
  id: string
  documentId: string
  candidateId: string | null
  name: string
  /** Who it's for, e.g. "Ada Lovelace, ETH Zurich". */
  targetLabel: string | null
  markdown: string
  createdAt: number
  updatedAt: number
}

export type DocumentTarget = { kind: "doc" | "version"; id: string }

// Where storage is blocked or full: this tab's memory, so drafts still
// open (they're lost on reload, as nothing could be kept).
const memory = new Map<string, string>()

function read<T>(key: string): T | null {
  // Memory holds only what storage refused, so it is the newer copy.
  let raw: string | null = memory.get(key) ?? null
  try {
    raw = raw ?? window.localStorage.getItem(key)
  } catch {
    /* storage unavailable */
  }
  try {
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function write(key: string, value: unknown): boolean {
  const raw = JSON.stringify(value)
  try {
    window.localStorage.setItem(key, raw)
    memory.delete(key)
    return true
  } catch {
    memory.set(key, raw)
    return false
  }
}

function remove(key: string) {
  memory.delete(key)
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* storage unavailable: nothing was kept there */
  }
}

function keys(prefix: string): string[] {
  const out = new Set([...memory.keys()].filter((k) => k.startsWith(prefix)))
  try {
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i)
      if (k?.startsWith(prefix)) out.add(k)
    }
  } catch {
    /* storage unavailable */
  }
  return [...out]
}

const copyKey = (user: string, t: DocumentTarget) => `${PREFIX}${user}.copy.${t.kind}.${t.id}`
const draftKey = (user: string, id: string) => `${PREFIX}${user}.draft.${id}`

export const loadCopy = (user: string, t: DocumentTarget) => read<LocalCopy>(copyKey(user, t))
export const storeCopy = (user: string, t: DocumentTarget, copy: LocalCopy) => write(copyKey(user, t), copy)
export const dropCopy = (user: string, t: DocumentTarget) => remove(copyKey(user, t))

export const loadDraft = (user: string, id: string) => read<DocumentDraft>(draftKey(user, id))
export const storeDraft = (user: string, draft: DocumentDraft) => write(draftKey(user, draft.id), draft)
export const dropDraft = (user: string, id: string) => remove(draftKey(user, id))

/** This account's unsaved variants, newest first. */
export function listDrafts(user: string): DocumentDraft[] {
  return keys(`${PREFIX}${user}.draft.`)
    .map((k) => read<DocumentDraft>(k))
    .filter((d): d is DocumentDraft => d !== null && typeof d.markdown === "string")
    .sort((a, b) => b.updatedAt - a.updatedAt)
}

/** Whether a saved CV has edits on this device the server hasn't got. */
export const hasCopy = (user: string, t: DocumentTarget) => loadCopy(user, t) !== null

/** Forget everything kept for one base CV (it was deleted). */
export function dropAllFor(user: string, documentId: string, versionIds: string[]) {
  dropCopy(user, { kind: "doc", id: documentId })
  for (const id of versionIds) dropCopy(user, { kind: "version", id })
  for (const d of listDrafts(user)) if (d.documentId === documentId) dropDraft(user, d.id)
}

export function newDraftId(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`
  }
}

/** A short fingerprint of a text (FNV-1a), to tell "same text" cheaply. */
export function hashText(text: string): string {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return `${text.length}:${(h >>> 0).toString(36)}`
}

import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import * as api from "../../lib/api"
import { ApiError } from "../../lib/api"
import { toastError, toastInfo } from "../../lib/toast"
import type { CvDocumentDetail, CvVersion, DocumentKind } from "../../lib/types"
import { type DocumentDraft, type DocumentTarget, dropCopy, hashText, loadCopy, storeCopy, storeDraft } from "./documentLocal"

/** Sync to the server once typing has paused this long. */
const SYNC_IDLE_MS = 5000
/** Write the device copy this soon after a keystroke. */
const STORE_DEBOUNCE_MS = 300
const RETRY_MIN_MS = 10_000
const RETRY_MAX_MS = 60_000

/**
 * - saved: the server has this text
 * - local: edited; kept on this device, syncing when typing pauses
 * - saving: a sync is on its way
 * - offline: the server can't be reached; kept on this device, retrying
 * - conflict: the server's text changed elsewhere; the student picks
 * - error: the server refused the save (kept on this device)
 * - draft: an unsaved variant, only on this device
 * - new: a new document nothing has been written in yet: not saved
 *   anywhere until the first edit or rename creates it
 */
export type SyncStatus = "saved" | "local" | "saving" | "offline" | "conflict" | "error" | "draft" | "new"

export type ServerText = { markdown: string; revision: number; title: string }

export type DocumentSource =
  | ({ kind: "doc" | "version"; id: string } & { server: ServerText })
  | { kind: "draft"; draft: DocumentDraft }
  | { kind: "new"; blank: NewDocument }

/** A document opened from a template but not created yet (no empty
 * documents in the account). `onCreated` hears of the row the first
 * edit made; the hook goes on syncing to it. */
export type NewDocument = {
  documentKind: DocumentKind
  folderId: string | null
  title: string
  markdown: string
  onCreated: (doc: CvDocumentDetail) => void
}

type Saved = CvDocumentDetail | CvVersion

function serverTitle(out: Saved): string {
  return "title" in out ? out.title : out.name
}

/**
 * Edits go to this device first (documentLocal) and to the server when typing pauses, the
 * tab is hidden or closed, the editor blurs, or on flush(). A 409 keeps the local text and
 * asks the student; a newer revision with the same text (a rename elsewhere) syncs over
 * silently. Mount one per open CV (key it by target); a new document's is set on creation.
 */
export function useDocumentSync(user: string, source: DocumentSource) {
  const qc = useQueryClient()
  const targetRef = React.useRef<DocumentTarget | null>(
    source.kind === "doc" || source.kind === "version" ? { kind: source.kind, id: source.id } : null,
  )
  const blank = source.kind === "new" ? source.blank : null

  // Resolved once: the server text against what this device kept.
  const [initial] = React.useState(() => {
    if (source.kind === "draft") {
      return { text: source.draft.markdown, title: source.draft.name, revision: 0, baseHash: "", dirty: false, status: "draft" as SyncStatus, conflict: null, restored: false }
    }
    if (source.kind === "new") {
      return { text: source.blank.markdown, title: source.blank.title, revision: 0, baseHash: "", dirty: false, status: "new" as SyncStatus, conflict: null, restored: false }
    }
    const server = source.server
    const serverHash = hashText(server.markdown)
    const local = targetRef.current ? loadCopy(user, targetRef.current) : null
    const differs = local && (local.markdown !== server.markdown || (local.title && local.title !== server.title))
    if (!local || !differs) {
      if (local && targetRef.current) dropCopy(user, targetRef.current)
      return { text: server.markdown, title: server.title, revision: server.revision, baseHash: serverHash, dirty: false, status: "saved" as SyncStatus, conflict: null, restored: false }
    }
    const sameBase = local.baseRevision === server.revision || local.baseHash === serverHash
    return {
      text: local.markdown,
      title: local.title ?? server.title,
      // Unchanged on the server since: carry on from its revision.
      revision: sameBase ? server.revision : local.baseRevision,
      baseHash: sameBase ? serverHash : local.baseHash,
      dirty: true,
      status: (sameBase ? "local" : "conflict") as SyncStatus,
      conflict: sameBase ? null : server,
      restored: true,
    }
  })

  const [text, setText] = React.useState(initial.text)
  const [title, setTitle] = React.useState(initial.title)
  const [status, setStatusState] = React.useState<SyncStatus>(initial.status)
  const [conflict, setConflict] = React.useState<ServerText | null>(initial.conflict)

  const textRef = React.useRef(initial.text)
  const titleRef = React.useRef(initial.title)
  const pendingTitle = React.useRef<string | null>(
    (source.kind === "doc" || source.kind === "version") && initial.title !== source.server.title ? initial.title : null,
  )
  const revision = React.useRef(initial.revision)
  const baseHash = React.useRef(initial.baseHash)
  const dirty = React.useRef(initial.dirty)
  const statusRef = React.useRef<SyncStatus>(initial.status)
  const inFlight = React.useRef<Promise<boolean> | null>(null)
  const idleTimer = React.useRef<number | undefined>(undefined)
  const storeTimer = React.useRef<number | undefined>(undefined)
  const retryTimer = React.useRef<number | undefined>(undefined)
  const retryDelay = React.useRef(RETRY_MIN_MS)
  const draftRef = React.useRef(source.kind === "draft" ? source.draft : null)
  // Saved as a variant, discarded or deleted: keep nothing more.
  const gone = React.useRef(false)

  const setStatus = React.useCallback((s: SyncStatus) => {
    statusRef.current = s
    setStatusState(s)
  }, [])

  const persist = React.useCallback(() => {
    window.clearTimeout(storeTimer.current)
    if (gone.current) return
    const draft = draftRef.current
    if (draft) {
      const next = { ...draft, markdown: textRef.current, name: titleRef.current, updatedAt: Date.now() }
      draftRef.current = next
      storeDraft(user, next)
      return
    }
    if (!targetRef.current || (!dirty.current && pendingTitle.current === null)) return
    storeCopy(user, targetRef.current, {
      markdown: textRef.current,
      title: pendingTitle.current ?? undefined,
      baseRevision: revision.current,
      baseHash: baseHash.current,
      updatedAt: Date.now(),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
  }, [user])

  const fetchLatest = React.useCallback(async (): Promise<ServerText> => {
    if (!targetRef.current) throw new Error("No server copy")
    if (targetRef.current.kind === "version") {
      const v = await api.getCvVersion(targetRef.current.id)
      return { markdown: v.markdown, revision: v.revision, title: v.name }
    }
    const d = await api.getCvDocument(targetRef.current.id)
    return { markdown: d.markdown, revision: d.revision, title: d.title }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
  }, [])

  const cacheSaved = React.useCallback(
    (out: Saved) => {
      if (!targetRef.current) return
      qc.setQueryData(targetRef.current.kind === "version" ? ["document-version", targetRef.current.id] : ["document", targetRef.current.id], out)
      void qc.invalidateQueries({ queryKey: ["documents"] })
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
    [qc],
  )

  const syncRef = React.useRef<() => Promise<boolean>>(async () => true)

  const scheduleRetry = React.useCallback(() => {
    window.clearTimeout(retryTimer.current)
    retryTimer.current = window.setTimeout(() => void syncRef.current(), retryDelay.current)
    retryDelay.current = Math.min(retryDelay.current * 2, RETRY_MAX_MS)
  }, [])

  /** A new document's first save: it is created only once something
   * has been written in it or it has been renamed. */
  const create = React.useCallback(async (): Promise<boolean> => {
    if (!blank || targetRef.current || gone.current) return true
    if (textRef.current === blank.markdown && pendingTitle.current === null) return true
    window.clearTimeout(retryTimer.current)
    const sentTitle = titleRef.current
    setStatus("saving")
    try {
      const out = await api.createCvFromText({
        title: sentTitle,
        markdown: textRef.current,
        kind: blank.documentKind,
        folder_id: blank.folderId,
      })
      targetRef.current = { kind: "doc", id: out.id }
      revision.current = out.revision
      baseHash.current = hashText(out.markdown)
      retryDelay.current = RETRY_MIN_MS
      // Typed or renamed while it was being created: sync that next.
      dirty.current = textRef.current !== out.markdown
      pendingTitle.current = titleRef.current === out.title ? null : titleRef.current
      cacheSaved(out)
      blank.onCreated(out)
      if (dirty.current || pendingTitle.current !== null) {
        persist()
        setStatus("local")
        idleTimer.current = window.setTimeout(() => void syncRef.current(), SYNC_IDLE_MS)
      } else {
        setStatus("saved")
      }
      return true
    } catch (err) {
      if (err instanceof ApiError) {
        setStatus("error")
        toastError(err, "Couldn't create the document")
      } else {
        setStatus("offline")
        scheduleRetry()
      }
      return false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
  }, [persist, cacheSaved, setStatus, scheduleRetry])

  const syncOnce = React.useCallback(async (): Promise<boolean> => {
    if (!targetRef.current) return create()
    if (gone.current) return true
    if (statusRef.current === "conflict") return false
    if (!dirty.current && pendingTitle.current === null) {
      if (statusRef.current !== "saved") {
        dropCopy(user, targetRef.current)
        setStatus("saved")
      }
      return true
    }
    window.clearTimeout(idleTimer.current)
    window.clearTimeout(retryTimer.current)
    persist()
    const sent = textRef.current
    const sentTitle = pendingTitle.current
    const body = {
      base_revision: revision.current,
      ...(dirty.current ? { markdown: sent } : {}),
      ...(sentTitle !== null ? { title: sentTitle } : {}),
    }
    setStatus("saving")
    try {
      let out: Saved
      try {
        out = targetRef.current.kind === "version" ? await api.saveCvVersion(targetRef.current.id, body) : await api.saveCvDocument(targetRef.current.id, body)
      } catch (err) {
        const reason = err instanceof ApiError && err.status === 409 ? (err.detail as { reason?: string } | null)?.reason : null
        if (reason !== "revision") throw err
        // Saved elsewhere since. Only a rename (same text) syncs over it.
        const latest = await fetchLatest()
        if (hashText(latest.markdown) !== baseHash.current) {
          setConflict(latest)
          setStatus("conflict")
          persist()
          return false
        }
        revision.current = latest.revision
        out = targetRef.current.kind === "version"
          ? await api.saveCvVersion(targetRef.current.id, { ...body, base_revision: latest.revision })
          : await api.saveCvDocument(targetRef.current.id, { ...body, base_revision: latest.revision })
      }
      revision.current = out.revision
      baseHash.current = hashText(out.markdown)
      retryDelay.current = RETRY_MIN_MS
      if (pendingTitle.current === sentTitle) pendingTitle.current = null
      dirty.current = textRef.current !== out.markdown
      if (pendingTitle.current === null && titleRef.current !== serverTitle(out) && sentTitle !== null) {
        titleRef.current = serverTitle(out)
        setTitle(serverTitle(out))
      }
      cacheSaved(out)
      if (dirty.current || pendingTitle.current !== null) {
        persist()
        setStatus("local")
        window.clearTimeout(idleTimer.current)
        idleTimer.current = window.setTimeout(() => void syncRef.current(), SYNC_IDLE_MS)
      } else {
        dropCopy(user, targetRef.current)
        setStatus("saved")
      }
      return true
    } catch (err) {
      persist()
      if (err instanceof ApiError) {
        setStatus("error")
        toastError(err, "Not saved yet. Your edits are kept on this device")
      } else {
        // No answer at all: the network, not the server.
        setStatus("offline")
        scheduleRetry()
      }
      return false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
  }, [user, create, persist, fetchLatest, cacheSaved, setStatus, scheduleRetry])

  /** Sync now (one at a time; edits made meanwhile follow right after). */
  const flush = React.useCallback(async (): Promise<boolean> => {
    if (!targetRef.current && !blank) {
      persist()
      return true
    }
    while (inFlight.current) await inFlight.current
    const p = syncOnce()
    inFlight.current = p
    try {
      return await p
    } finally {
      inFlight.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
  }, [syncOnce, persist])
  syncRef.current = flush

  const edit = React.useCallback(
    (next: string) => {
      if (next === textRef.current) return
      textRef.current = next
      setText(next)
      window.clearTimeout(storeTimer.current)
      storeTimer.current = window.setTimeout(persist, STORE_DEBOUNCE_MS)
      if (!targetRef.current) {
        // A new document: the first edit creates it.
        if (blank && statusRef.current !== "saving") void syncRef.current()
        return
      }
      dirty.current = true
      const s = statusRef.current
      if (s === "conflict") return
      if (s !== "offline" && s !== "saving") setStatus("local")
      window.clearTimeout(idleTimer.current)
      idleTimer.current = window.setTimeout(() => void syncRef.current(), SYNC_IDLE_MS)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
    [persist, setStatus],
  )

  const rename = React.useCallback(
    (next: string) => {
      const clean = next.trim()
      if (!clean || clean === titleRef.current) return
      titleRef.current = clean
      setTitle(clean)
      if (!targetRef.current && !blank) {
        persist()
        return
      }
      pendingTitle.current = clean
      persist()
      if (statusRef.current !== "conflict") void flush()
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
    [persist, flush],
  )

  /** After a 409: keep this device's text (sync it over the server's) or
   * take the server's. */
  const resolveConflict = React.useCallback(
    (choice: "mine" | "theirs") => {
      const server = conflict
      if (!server || !targetRef.current) return
      revision.current = server.revision
      baseHash.current = hashText(server.markdown)
      setConflict(null)
      if (choice === "theirs") {
        textRef.current = server.markdown
        setText(server.markdown)
        titleRef.current = server.title
        setTitle(server.title)
        pendingTitle.current = null
        dirty.current = false
        dropCopy(user, targetRef.current)
        setStatus("saved")
        qc.setQueryData(targetRef.current.kind === "version" ? ["document-version", targetRef.current.id] : ["document", targetRef.current.id], (old: object | undefined) =>
          old ? { ...old, markdown: server.markdown, revision: server.revision } : old,
        )
        return
      }
      dirty.current = textRef.current !== server.markdown
      setStatus("local")
      void flush()
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
    [conflict, user, flush, setStatus, qc],
  )

  /** The server changed the text itself (an accepted suggestion). */
  const applyServer = React.useCallback(
    (markdown: string, rev: number) => {
      textRef.current = markdown
      setText(markdown)
      revision.current = rev
      baseHash.current = hashText(markdown)
      dirty.current = false
      if (targetRef.current && pendingTitle.current === null) {
        dropCopy(user, targetRef.current)
        setStatus("saved")
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
    [user, setStatus],
  )

  // Restored work: say so, then send it on.
  React.useEffect(() => {
    if (!initial.restored) return
    if (initial.status === "conflict") {
      toastInfo("Restored edits from this device. This CV changed elsewhere since, so choose which to keep.")
    } else {
      toastInfo("Restored edits kept on this device; syncing them now.")
      void flush()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per open CV
  }, [])

  // Hidden, closed or offline-then-online: keep the copy and sync.
  React.useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") {
        persist()
        void flush()
      }
    }
    const onLeave = () => {
      persist()
      void flush()
    }
    const onOnline = () => {
      if (statusRef.current === "offline") void flush()
    }
    document.addEventListener("visibilitychange", onHide)
    window.addEventListener("pagehide", onLeave)
    window.addEventListener("online", onOnline)
    return () => {
      document.removeEventListener("visibilitychange", onHide)
      window.removeEventListener("pagehide", onLeave)
      window.removeEventListener("online", onOnline)
    }
  }, [persist, flush])

  // Leaving this CV (another CV, the list): keep and send what's left.
  React.useEffect(
    () => () => {
      window.clearTimeout(idleTimer.current)
      window.clearTimeout(retryTimer.current)
      persist()
      if (!targetRef.current) void create()
      else if (!gone.current && statusRef.current !== "conflict" && (dirty.current || pendingTitle.current !== null)) void syncOnce()
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unmount only
    [],
  )

  /** Stop keeping or syncing this CV (saved as a variant, discarded, deleted). */
  const forget = React.useCallback(() => {
    gone.current = true
    window.clearTimeout(idleTimer.current)
    window.clearTimeout(storeTimer.current)
    window.clearTimeout(retryTimer.current)
    if (targetRef.current) dropCopy(user, targetRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the source is fixed for the hook's life
  }, [user])

  return {
    text,
    title,
    status,
    conflict,
    /** Edits since the last sync, on this device only. */
    hasUnsynced: () => dirty.current || pendingTitle.current !== null,
    /** The text as typed this instant (state lags a render). */
    current: () => textRef.current,
    revision: () => revision.current,
    edit,
    rename,
    flush,
    resolveConflict,
    applyServer,
    persist,
    forget,
  }
}

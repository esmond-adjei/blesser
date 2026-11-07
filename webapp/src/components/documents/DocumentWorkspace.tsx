import * as React from "react"
import { createPortal } from "react-dom"
import { useNavigate } from "react-router-dom"
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Cloud,
  CloudCheck,
  CloudOff,
  LoaderCircle,
  Save,
  TriangleAlert,
  X,
} from "lucide-react"
import * as api from "../../lib/api"
import { ApiError } from "../../lib/api"
import { saveFile } from "../../lib/download"
import { usePaneWidth } from "../../lib/paneWidth"
import { useChatModel } from "../../lib/providers"
import { useCvSuggestions, useDocumentFolders } from "../../lib/queries"
import { toastError, toastInfo, toastSuccess } from "../../lib/toast"
import type { CvDocumentDetail, CvSuggestAction, CvSuggestion, CvVersion } from "../../lib/types"
import { cn } from "../../lib/utils"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"
import { Button } from "../ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Alert, AlertDescription, Skeleton, SkeletonStack } from "../ui/feedback"
import { Markdown } from "../ui/MarkdownLazy"
import { BaseUpdatedBar } from "./BaseUpdated"
import { ChecksButton, LengthMeter } from "./LimitsAndChecks"
import { CommandPalette, type PaletteCommand } from "./CommandPalette"
import { dropDraft } from "./documentLocal"
import { ACTION_LABEL, looksLikeUrl, outline, toPlainText, wordCount } from "./documentText"
import { DocumentHeader, type ExportChoice } from "./DocumentHeader"
import { DocumentToolbar } from "./DocumentToolbar"
import type { EditorCommand } from "./editor/format"
import type { EditorStatus, MarkdownEditorHandle, SelectionBarInfo } from "./editor/MarkdownEditor"
import { SHORTCUTS, shortcutLabel } from "./editor/shortcuts"
import { type LinkRequest, LinkPopover } from "./LinkPopover"
import { SelectionBar } from "./SelectionBar"
import { GradisChat } from "../gradis/GradisChat"
import { useGradis } from "../gradis/GradisProvider"
import { type PanelTab, type SuggestionRequest, SuggestionsPanel } from "./SuggestionsPanel"
import { KIND, kindOf } from "./kinds"
import { safeName } from "./tailor"
import { TailorPicker } from "./TailorPicker"
import { type DocumentSource, type SyncStatus, useDocumentSync } from "./useDocumentSync"

// CodeMirror is most of this page's weight: its own chunk.
const MarkdownEditor = React.lazy(() =>
  import("./editor/MarkdownEditor").then((m) => ({ default: m.MarkdownEditor })),
)

function wide(px: number): boolean {
  return typeof window === "undefined" || window.matchMedia(`(min-width: ${px}px)`).matches
}

/** The suggestions panel's width: 18rem (the outline's) up to 40rem, and
 * never more than about half the window, so the page keeps room. */
const PANEL_MIN = 288
const panelMax = () => Math.max(PANEL_MIN, Math.min(640, Math.round(window.innerWidth * 0.45)))

function useRemembered(key: string, initial: () => boolean): [boolean, React.Dispatch<React.SetStateAction<boolean>>] {
  const [value, setValue] = React.useState(() => {
    try {
      const stored = window.localStorage.getItem(key)
      if (stored === "1" || stored === "0") return stored === "1"
    } catch {
      /* storage unavailable */
    }
    return initial()
  })
  React.useEffect(() => {
    try {
      window.localStorage.setItem(key, value ? "1" : "0")
    } catch {
      /* storage unavailable: remembered for this visit only */
    }
  }, [key, value])
  return [value, setValue]
}

const NO_MARKS = { bold: false, italic: false, underline: false, link: false }
const LAYOUT_DELAY_MS = 600
/** How long after the last saved edit the consistency checks run again. */
const CHECKS_DELAY_MS = 2500

const STATUS: Record<SyncStatus, { label: string; short: string; icon: React.ElementType; tone?: string }> = {
  saved: { label: "Saved", short: "Saved", icon: CloudCheck },
  local: { label: "Saved on this device", short: "Edited", icon: Cloud },
  saving: { label: "Saving…", short: "Saving…", icon: LoaderCircle },
  offline: { label: "Offline, changes kept on this device", short: "Offline", icon: CloudOff, tone: "text-caution" },
  error: { label: "Not saved, changes kept on this device", short: "Not saved", icon: TriangleAlert, tone: "text-caution" },
  conflict: { label: "Changed elsewhere, not saved", short: "Conflict", icon: TriangleAlert, tone: "text-critical" },
  draft: { label: "Unsaved variant", short: "Unsaved", icon: TriangleAlert, tone: "text-caution" },
  new: { label: "Not saved until you start writing", short: "New", icon: Cloud },
}

function SyncBadge({ status, onRetry }: { status: SyncStatus; onRetry: () => void }) {
  const s = STATUS[status]
  const Icon = s.icon
  const retry = status === "error" || status === "offline"
  const body = (
    <>
      <Icon className={cn("size-4 shrink-0", status === "saving" && "animate-spin")} />
      {/* Saved is the quiet state: the icon alone, its words in the tooltip. */}
      {status !== "saved" && (
        <>
          <span className="hidden truncate md:inline">{s.label}</span>
          <span className="truncate md:hidden">{s.short}</span>
        </>
      )}
    </>
  )
  const cls = cn("inline-flex min-w-0 shrink items-center gap-1.5 text-xs text-muted-foreground", s.tone)
  return retry ? (
    <button type="button" onClick={onRetry} data-tooltip={`${s.label}. Click to retry now.`} className={cn(cls, "rounded px-1 hover:bg-accent")} aria-live="polite">
      {body}
    </button>
  ) : (
    <span className={cn(cls, status === "draft" && "g-pill g-pill--caution")} data-tooltip={s.label} aria-live="polite">
      {body}
    </span>
  )
}

/** Keyed per document by the parent, so switching starts fresh. */
export function DocumentWorkspace({
  user,
  source,
  doc,
  version,
}: {
  user: string
  source: DocumentSource
  /** The base CV (its versions, original file, text for comparing). */
  doc: CvDocumentDetail
  version: CvVersion | null
}) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const model = useChatModel()
  const sync = useDocumentSync(user, source)
  const draft = source.kind === "draft" ? source.draft : null
  const versionId = source.kind === "version" ? source.id : null
  const isVariant = source.kind === "version" || source.kind === "draft"
  // A new document nothing has been written in: not created yet, so
  // nothing that needs it on the server (suggestions, checks, limits,
  // exports, tailoring) is offered until the first edit creates it.
  const unborn = !doc.id
  const docKind = KIND[kindOf(doc.kind)]
  const suggestions = useCvSuggestions(draft || unborn ? null : doc.id, versionId)
  const editor = React.useRef<MarkdownEditorHandle | null>(null)

  const [edStatus, setEdStatus] = React.useState<EditorStatus>({ block: "normal", marks: NO_MARKS, canUndo: false, canRedo: false, inTable: false })
  const [editorReady, setEditorReady] = React.useState(false)
  // Keys from when documents were CVs, kept so the choices stay remembered.
  const [outlineOpen, setOutlineOpen] = useRemembered("graduator.cv.outline", () => wide(1280))
  const [pagesOn, setPagesOn] = useRemembered("graduator.cv.pages", () => true)
  const [link, setLink] = React.useState<LinkRequest | null>(null)
  const [currentHeading, setCurrentHeading] = React.useState<number | null>(null)
  const canvas = React.useRef<HTMLElement | null>(null)
  const [panelOpen, setPanelOpen] = React.useState(() => wide(1024) && !draft)
  const [compare, setCompare] = React.useState(false)
  const [paletteOpen, setPaletteOpen] = React.useState(false)
  const [pickerOpen, setPickerOpen] = React.useState(false)
  const [busyId, setBusyId] = React.useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const [leaveTo, setLeaveTo] = React.useState<string | null>(null)
  const [savingVariant, setSavingVariant] = React.useState(false)
  const [bar, setBar] = React.useState<SelectionBarInfo | null>(null)
  const [requests, setRequests] = React.useState<SuggestionRequest[]>([])
  const [activeId, setActiveId] = React.useState<string | null>(null)
  const [panelTab, setPanelTab] = React.useState<PanelTab>("review")
  const panel = usePaneWidth("graduator.documents.panel.width", PANEL_MIN, PANEL_MIN, panelMax())
  const [resizing, setResizing] = React.useState(false)
  // A drag writes the width straight onto the panel and saves it once at the end:
  // re-rendering the editor on every pointer move stutters.
  const panelBox = React.useRef<HTMLDivElement | null>(null)
  const dragWidth = React.useRef<number | null>(null)
  const endResize = () => {
    if (dragWidth.current !== null) panel.setWidth(dragWidth.current)
    dragWidth.current = null
    setResizing(false)
  }
  const gradis = useGradis()
  const chatPane = React.useRef<HTMLDivElement | null>(null)
  const [applyingAll, setApplyingAll] = React.useState(false)
  const [name, setName] = React.useState(sync.title)
  const nameRef = React.useRef<HTMLInputElement | null>(null)
  const folders = useDocumentFolders()
  React.useEffect(() => setName(sync.title), [sync.title])


  /** Sync first; an unsaved variant asks what to do. */
  async function go(to: string) {
    if (draft) {
      setLeaveTo(to)
      return
    }
    await sync.flush()
    navigate(to)
  }

  function leaveDraft(choice: "keep" | "discard") {
    const to = leaveTo ?? "/documents"
    setLeaveTo(null)
    if (choice === "discard" && draft) {
      sync.forget()
      dropDraft(user, draft.id)
    } else {
      sync.persist()
    }
    navigate(to)
  }

  // Closing the tab: an unsaved variant (or a conflict) warns. Saved
  // CVs need no warning: the device copy is kept and synced next time.
  const statusNow = React.useRef(sync.status)
  statusNow.current = sync.status
  const { persist } = sync
  React.useEffect(() => {
    const onLeave = (e: BeforeUnloadEvent) => {
      persist()
      if (draft || statusNow.current === "conflict") {
        e.preventDefault()
        e.returnValue = ""
      }
    }
    window.addEventListener("beforeunload", onLeave)
    return () => window.removeEventListener("beforeunload", onLeave)
  }, [draft, persist])


  async function saveVariant() {
    if (!draft || savingVariant) return
    sync.persist()
    setSavingVariant(true)
    try {
      const v = await api.createCvVersion(doc.id, {
        candidate_id: draft.candidateId ?? undefined,
        name: (name.trim() || sync.title).slice(0, 160),
        markdown: sync.current(),
        new: true,
      })
      sync.forget()
      dropDraft(user, draft.id)
      qc.setQueryData(["document-version", v.id], v)
      void qc.invalidateQueries({ queryKey: ["documents"] })
      void qc.invalidateQueries({ queryKey: ["document", doc.id] })
      toastSuccess(`${v.name} saved`)
      const to = `/documents/${doc.id}?version=${v.id}`
      if (leaveTo) {
        setLeaveTo(null)
        navigate(leaveTo)
      } else {
        navigate(to, { replace: true })
      }
    } catch (err) {
      toastError(err, "Couldn't save the variant")
    } finally {
      setSavingVariant(false)
    }
  }


  async function moveTo(folderId: string | null) {
    try {
      const out = await api.moveDocument(doc.id, folderId)
      qc.setQueryData(["document", doc.id], (old: CvDocumentDetail | undefined) => (old ? { ...old, folder_id: out.folder_id } : old))
      void qc.invalidateQueries({ queryKey: ["documents"] })
      void qc.invalidateQueries({ queryKey: ["document-folders"] })
      const f = folders.data?.find((x) => x.id === folderId)
      toastSuccess(f ? `Moved to ${f.name}` : "Removed from its folder")
    } catch (err) {
      toastError(err, "Couldn't move it")
    }
  }

  function commitName() {
    const clean = name.trim()
    if (!clean) {
      setName(sync.title)
      return
    }
    sync.rename(clean)
  }

  async function doDelete() {
    setConfirmDelete(false)
    if (unborn) {
      sync.forget()
      navigate("/documents")
      return
    }
    if (draft) {
      sync.forget()
      dropDraft(user, draft.id)
      navigate("/documents")
      return
    }
    try {
      if (versionId) await api.deleteCvVersion(versionId)
      else await api.deleteCvDocument(doc.id)
      sync.forget()
      void qc.invalidateQueries({ queryKey: ["documents"] })
      void qc.invalidateQueries({ queryKey: ["document", doc.id] })
      toastSuccess(`${sync.title} deleted`)
      navigate("/documents")
    } catch (err) {
      toastError(err, "Delete failed")
    }
  }


  const refreshSuggestions = React.useCallback(
    () => qc.invalidateQueries({ queryKey: ["document-suggestions", doc.id, versionId] }),
    [qc, doc.id, versionId],
  )

  async function accept(s: CvSuggestion, opts: { replace?: string; confirm: boolean }) {
    if (!(await sync.flush())) {
      toastInfo("Sync your edits first: the suggestion applies to the saved text.")
      return
    }
    setBusyId(s.id)
    try {
      const out = await api.acceptCvSuggestion(s.id, { replace: opts.replace, confirm_new_terms: opts.confirm })
      sync.applyServer(out.markdown, out.revision)
      qc.setQueryData(
        s.version_id ? ["document-version", s.version_id] : ["document", s.document_id],
        (old: { markdown: string; revision: number } | undefined) =>
          old ? { ...old, markdown: out.markdown, revision: out.revision } : old,
      )
      editor.current?.highlight(null)
      setActiveId(null)
    } catch (err) {
      const detail = err instanceof ApiError ? (err.detail as { reason?: string; new_terms?: string[] } | null) : null
      if (detail?.reason === "new_terms") {
        toastInfo(`Your edit adds words your documents don't mention (${(detail.new_terms ?? []).join(", ")}). Tick the box to confirm they're true.`)
      } else if (detail?.reason === "stale") {
        toastInfo("Its text was edited since, so it wasn't applied. Get a fresh suggestion instead.")
      } else if (detail?.reason === "revision") {
        toastInfo("This changed elsewhere. Reload it, then accept again.")
      } else {
        toastError(err, "Couldn't apply it")
      }
    } finally {
      setBusyId(null)
      void refreshSuggestions()
    }
  }

  async function reject(s: CvSuggestion) {
    setBusyId(s.id)
    try {
      await api.rejectCvSuggestion(s.id)
    } catch (err) {
      toastError(err)
    } finally {
      setBusyId(null)
      void refreshSuggestions()
    }
  }

  /** A fresh suggestion in place of a stale one, against the current text. */
  async function refreshSuggestion(s: CvSuggestion) {
    if (!(await sync.flush())) {
      toastInfo("Sync your edits first: the fresh suggestion is made against the saved text.")
      return
    }
    const id = `req-${++requestSeq.current}`
    setRequests((r) => [{ id, label: "Fresh suggestion", excerpt: s.find.replace(/\s+/g, " ").trim() }, ...r])
    setBusyId(s.id)
    try {
      await api.refreshCvSuggestion(s.id, { model })
    } catch (err) {
      const reason = err instanceof ApiError ? (err.detail as { reason?: string } | null)?.reason : null
      if (reason === "gone") toastInfo("The text it changed is gone. Select the text you want changed and ask again.")
      else if (!(err instanceof ApiError && err.status === 402)) toastError(err, "Couldn't get a fresh suggestion")
    } finally {
      setRequests((r) => r.filter((x) => x.id !== id))
      setBusyId(null)
      void refreshSuggestions()
    }
  }


  const [lineageBusy, setLineageBusy] = React.useState(false)
  const markBaseSeen = React.useCallback(() => {
    if (!versionId) return
    qc.setQueryData(["document-version", versionId], (old: CvVersion | undefined) => (old ? { ...old, base_updated: false } : old))
    void qc.invalidateQueries({ queryKey: ["documents"] })
  }, [qc, versionId])

  async function suggestBaseChanges() {
    if (!versionId) return
    if (!(await sync.flush())) {
      toastInfo("Sync your edits first: the base's changes are matched against the saved text.")
      return
    }
    setLineageBusy(true)
    try {
      const out = await api.syncFromBase(versionId)
      markBaseSeen()
      setPanelOpen(true)
      const n = out.suggestions.length
      if (n && out.skipped) toastInfo(`${n} ${n === 1 ? "change" : "changes"} from the base to review. ${out.skipped} touch text you changed here: see them under Changes.`)
      else if (n) toastSuccess(`${n} ${n === 1 ? "change" : "changes"} from the base to review`)
      else toastInfo("The base's changes are all in parts you changed here. Copy what you want by hand.")
    } catch (err) {
      toastError(err, "Couldn't get the base's changes")
    } finally {
      setLineageBusy(false)
      void refreshSuggestions()
    }
  }

  async function keepAsIs() {
    if (!versionId) return
    setLineageBusy(true)
    try {
      await api.keepVersionAsIs(versionId)
      markBaseSeen()
    } catch (err) {
      toastError(err)
    } finally {
      setLineageBusy(false)
    }
  }

  function locateSuggestion(s: CvSuggestion) {
    if (compare) setCompare(false)
    setActiveId(s.id)
    window.setTimeout(() => {
      if (!editor.current?.highlight(s.find)) toastInfo("That text isn't in the document exactly once any more.")
    }, 0)
  }

  /** One at a time, as each changes the text the next applies to. Those adding words
   * the base CV never mentions wait for the student's check. */
  async function applyAll() {
    const waiting = (suggestions.data ?? [])
      .filter((s) => s.status === "pending" && s.applicable)
      .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""))
    if (waiting.length < 2 || applyingAll) return
    if (!(await sync.flush())) {
      toastInfo("Sync your edits first: suggestions apply to the saved text.")
      return
    }
    setApplyingAll(true)
    let applied = 0
    let skipped = 0
    try {
      for (const s of waiting) {
        if ((s.claim_check?.new_terms ?? []).length > 0) {
          skipped++
          continue
        }
        try {
          const out = await api.acceptCvSuggestion(s.id, {})
          sync.applyServer(out.markdown, out.revision)
          applied++
        } catch {
          skipped++
        }
      }
    } finally {
      setApplyingAll(false)
      editor.current?.highlight(null)
      setActiveId(null)
      void refreshSuggestions()
      void qc.invalidateQueries({ queryKey: versionId ? ["document-version", versionId] : ["document", doc.id] })
    }
    if (skipped) {
      toastInfo(`Applied ${applied}. ${skipped} ${skipped === 1 ? "needs" : "need"} a look first: check the words they add, then apply them one by one.`)
    } else {
      toastSuccess(`Applied ${applied} suggestions`)
    }
  }


  const tailorFor = draft ? null : (version?.professor_name ?? version?.target_label ?? null)
  const requestSeq = React.useRef(0)

  /** The text stays marked until the suggestion lands in the panel. */
  async function requestSuggestion(action: CvSuggestAction, instruction?: string) {
    const ed = editor.current
    const at = bar
    if (!ed || !at || draft) return
    if (unborn) {
      toastInfo(`Write something first: a new ${docKind.noun} is saved once you start.`)
      return
    }
    ed.closeBar()
    const id = `req-${++requestSeq.current}`
    const excerpt = at.text.replace(/\s+/g, " ").trim()
    ed.markLoading(id, at.from, at.to)
    setRequests((r) => [{ id, label: action === "custom" ? (instruction ?? ACTION_LABEL.custom) : ACTION_LABEL[action], excerpt }, ...r])
    setPanelOpen(true)
    try {
      // The server suggests against the saved text.
      if (!(await sync.flush())) {
        toastInfo("Couldn't save your latest edits, so there's nothing to suggest against yet. Try again in a moment.")
        return
      }
      // Wherever the marked text is now (typing may have moved it).
      const range = ed.loadingRange(id)
      const text = sync.current()
      if (!range || range.to <= range.from) return
      const out = await api.suggestForSelection(doc.id, {
        version_id: versionId,
        base_revision: sync.revision(),
        range,
        text: text.slice(range.from, range.to),
        action,
        instruction,
        model,
      })
      qc.setQueryData(["document-suggestions", doc.id, versionId], (old: CvSuggestion[] | undefined) => [...(old ?? []), ...out])
    } catch (err) {
      const reason = err instanceof ApiError ? (err.detail as { reason?: string } | null)?.reason : null
      if (reason === "revision" || reason === "range") toastInfo("The text changed while asking. Select it and ask again.")
      else if (!(err instanceof ApiError && err.status === 402)) toastError(err, "Couldn't get a suggestion")
    } finally {
      ed.unmarkLoading(id)
      setRequests((r) => r.filter((x) => x.id !== id))
      void refreshSuggestions()
    }
  }


  function chatAbout() {
    const at = bar
    editor.current?.closeBar()
    if (at) gradis.attachSelection(at.text)
    openChat()
  }

  function openChat() {
    setPanelOpen(true)
    setPanelTab("chat")
    // Once the tab shows: straight to typing.
    window.setTimeout(() => chatPane.current?.querySelector<HTMLTextAreaElement>("[data-gradis-composer] textarea")?.focus(), 50)
  }

  // Pending suggestions keep their text marked while they wait.
  const waitingFinds = React.useMemo(
    () => (suggestions.data ?? []).filter((s) => s.status === "pending" && s.applicable).map((s) => s.find),
    [suggestions.data],
  )
  React.useEffect(() => {
    if (!editorReady || compare) return
    editor.current?.setReviewMarks(waitingFinds)
  }, [waitingFinds, editorReady, compare])


  async function onExport(choice: ExportChoice) {
    const text = sync.current()
    try {
      if (choice === "copy-text" || choice === "copy-md") {
        await navigator.clipboard.writeText(choice === "copy-md" ? text : toPlainText(text))
        toastSuccess(choice === "copy-md" ? "Markdown copied" : "Text copied")
      } else if (choice === "md" || choice === "txt") {
        // From the text on screen: no round trip, works offline.
        const body = choice === "md" ? text : toPlainText(text)
        const type = choice === "md" ? "text/markdown;charset=utf-8" : "text/plain;charset=utf-8"
        saveFile(new Blob([body], { type }), `${safeName(sync.title)}.${choice}`)
      } else if (choice === "original") {
        const file = await api.downloadCvOriginal(doc.id)
        saveFile(file.blob, file.filename)
      } else {
        if (!(await sync.flush())) {
          toastInfo(`Couldn't save your latest edits, so the ${choice === "pdf" ? "PDF" : "Word file"} would miss them. Try again in a moment.`)
          return
        }
        const file = versionId ? await api.exportCvVersion(versionId, choice) : await api.exportCvDocument(doc.id, choice)
        saveFile(file.blob, file.filename)
      }
    } catch (err) {
      toastError(err, "Download failed")
    }
  }


  const keyActions = React.useRef({ save: () => {} })
  keyActions.current.save = () => {
    if (draft) void saveVariant()
    else void sync.flush()
  }
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      if (mod && e.key === "/") {
        e.preventDefault()
        setPaletteOpen((o) => !o)
      } else if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault()
        keyActions.current.save()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const exec = React.useCallback((cmd: EditorCommand) => editor.current?.exec(cmd), [])
  const pending = (suggestions.data ?? []).filter((s) => s.status === "pending").length
  const headings = React.useMemo(() => outline(sync.text), [sync.text])
  const target = draft?.targetLabel ?? version?.target_label ?? null


  const openLink = React.useCallback(async () => {
    const ed = editor.current
    if (!ed) return
    const label = ed.selection()
    const at = ed.caretRect()
    let url = looksLikeUrl(label) ? label.trim() : ""
    if (!url) {
      // Only when the browser already allows it: never a permission prompt.
      try {
        const perm = await navigator.permissions?.query({ name: "clipboard-read" as PermissionName })
        if (perm?.state === "granted") {
          const clip = (await navigator.clipboard.readText()).trim()
          if (looksLikeUrl(clip)) url = clip
        }
      } catch {
        /* no clipboard access: start empty */
      }
    }
    setLink({ left: at?.left ?? window.innerWidth / 2 - 160, top: at?.top ?? 120, bottom: at?.bottom ?? 120, label, url })
  }, [])

  // A variant's own limits, else its base's.

  const ownLimits = {
    word_limit: (versionId ? version?.word_limit : doc.word_limit) ?? null,
    page_limit: (versionId ? version?.page_limit : doc.page_limit) ?? null,
  }
  const baseLimits = versionId
    ? { word_limit: version?.base_word_limit ?? doc.word_limit, page_limit: version?.base_page_limit ?? doc.page_limit }
    : null
  const limits = {
    word_limit: ownLimits.word_limit ?? baseLimits?.word_limit ?? (draft ? doc.word_limit : null),
    page_limit: ownLimits.page_limit ?? baseLimits?.page_limit ?? (draft ? doc.page_limit : null),
  }
  const [pages, setPages] = React.useState<number | null>(null)

  async function saveLimits(next: { word_limit: number | null; page_limit: number | null }): Promise<boolean> {
    try {
      if (versionId) {
        const v = await api.setVersionLimits(versionId, next)
        qc.setQueryData(["document-version", versionId], (old: CvVersion | undefined) => (old ? { ...old, ...next, revision: old.revision } : v))
      } else {
        await api.setDocumentLimits(doc.id, next)
        qc.setQueryData(["document", doc.id], (old: typeof doc | undefined) => (old ? { ...old, ...next } : old))
      }
      void qc.invalidateQueries({ queryKey: ["documents"] })
      return true
    } catch (err) {
      toastError(err, "Couldn't save the limits")
      return false
    }
  }


  const layoutFor = React.useRef("")
  const textNow = React.useRef(sync.current)
  textNow.current = sync.current
  // The page count is wanted for a page limit even with the breaks hidden.
  const wantLayout = pagesOn || Boolean(limits.page_limit)
  React.useEffect(() => {
    if (!editorReady || compare) {
      // The editor comes back fresh after comparing: draw them again.
      layoutFor.current = ""
      return
    }
    if (!pagesOn) editor.current?.setPageBreaks([])
    if (!wantLayout) {
      layoutFor.current = ""
      return
    }
    const text = sync.text
    if (text === layoutFor.current) return
    const t = window.setTimeout(() => {
      api
        .cvLayout(text)
        .then((out) => {
          // Only for the text it was made from: newer typing asks again.
          if (textNow.current() !== text) return
          layoutFor.current = text
          setPages(out.pages)
          if (pagesOn) editor.current?.setPageBreaks(out.breaks)
        })
        .catch(() => {
          /* offline or failing: keep the breaks already shown */
        })
    }, layoutFor.current ? LAYOUT_DELAY_MS : 0)
    return () => window.clearTimeout(t)
  }, [sync.text, pagesOn, wantLayout, editorReady, compare])

  // Consistency checks are read-only, on the saved text.

  const [checkedText, setCheckedText] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (draft || sync.status !== "saved") return
    const t = window.setTimeout(() => setCheckedText(sync.text), checkedText === null ? 0 : CHECKS_DELAY_MS)
    return () => window.clearTimeout(t)
  }, [draft, sync.status, sync.text, checkedText])
  const checks = useQuery({
    queryKey: ["document-checks", doc.id, versionId, checkedText],
    queryFn: () => api.getDocumentChecks(doc.id, versionId),
    enabled: !draft && !unborn && checkedText !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })

  function locateFinding(f: { line: number; quote: string }) {
    if (compare) setCompare(false)
    setActiveId(null)
    window.setTimeout(() => {
      if (!editor.current?.highlightOnLine(f.line, f.quote)) toastInfo("That text has changed since.")
    }, 0)
  }


  React.useEffect(() => {
    const el = canvas.current
    if (!el || !outlineOpen || compare) return
    let frame = 0
    const update = () => {
      frame = 0
      const pos = editor.current?.posAtY(el.getBoundingClientRect().top + 96)
      if (pos == null) return
      let current: number | null = null
      for (const h of headings) {
        if (h.pos <= pos) current = h.pos
        else break
      }
      setCurrentHeading(current ?? headings[0]?.pos ?? null)
    }
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update)
    }
    update()
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => {
      el.removeEventListener("scroll", onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [headings, outlineOpen, compare, editorReady])

  const fmt = (label: string, key: keyof typeof SHORTCUTS, cmd: EditorCommand): PaletteCommand => ({
    id: `fmt-${key}`,
    label,
    hint: shortcutLabel(SHORTCUTS[key]),
    run: () => exec(cmd),
  })
  const deleteLabel = unborn ? `Discard this ${docKind.noun}` : draft ? "Discard this variant" : versionId ? "Delete this variant" : `Delete this ${docKind.noun}`
  const commands: PaletteCommand[] = [
    ...(draft ? [{ id: "save-variant", label: "Save variant", hint: shortcutLabel(SHORTCUTS.save), run: () => void saveVariant() }] : []),
    { id: "tailor", label: "Tailor for a professor…", run: () => setPickerOpen(true) },
    { id: "suggest", label: "Suggest a change to the selection", hint: shortcutLabel(SHORTCUTS.suggest), disabled: compare, run: () => editor.current?.openBar() },
    { id: "sync", label: "Save now", hint: shortcutLabel(SHORTCUTS.save), disabled: !!draft || unborn, run: () => void sync.flush() },
    fmt("Bold", "bold", { type: "bold" }),
    fmt("Italic", "italic", { type: "italic" }),
    fmt("Underline", "underline", { type: "underline" }),
    { id: "fmt-link", label: "Insert link", hint: shortcutLabel(SHORTCUTS.link), run: () => void openLink() },
    fmt("Bulleted list", "bullets", { type: "list", ordered: false }),
    fmt("Numbered list", "numbers", { type: "list", ordered: true }),
    { id: "table", label: "Insert table", run: () => exec({ type: "table", rows: 3, cols: 3 }) },
    { id: "rule", label: "Insert horizontal line", run: () => exec({ type: "rule" }) },
    fmt("Normal text", "normal", { type: "block", style: "normal" }),
    { id: "fmt-title", label: "Title", run: () => exec({ type: "block", style: "title" }) },
    fmt("Heading 1", "h1", { type: "block", style: "h1" }),
    fmt("Heading 2", "h2", { type: "block", style: "h2" }),
    fmt("Heading 3", "h3", { type: "block", style: "h3" }),
    { id: "find", label: "Find and replace", hint: shortcutLabel(SHORTCUTS.find), run: () => exec({ type: "find" }) },
    { id: "pdf", label: "Download PDF", disabled: !!draft || unborn, run: () => void onExport("pdf") },
    { id: "docx", label: "Download Word (.docx)", disabled: !!draft || unborn, run: () => void onExport("docx") },
    { id: "md", label: "Download Markdown", run: () => void onExport("md") },
    { id: "txt", label: "Download text", run: () => void onExport("txt") },
    { id: "original", label: "Download the uploaded file", disabled: !doc.has_original, run: () => void onExport("original") },
    { id: "copy-text", label: "Copy as text", run: () => void onExport("copy-text") },
    { id: "copy-md", label: "Copy as Markdown", run: () => void onExport("copy-md") },
    { id: "compare", label: compare ? "Stop comparing" : "Compare with the base", disabled: !isVariant, run: () => setCompare((c) => !c) },
    { id: "base", label: "Open the base", disabled: !isVariant, run: () => void go(`/documents/${doc.id}`) },
    { id: "outline", label: outlineOpen ? "Hide outline" : "Show outline", run: () => setOutlineOpen((o) => !o) },
    { id: "pages", label: pagesOn ? "Hide page breaks" : "Show page breaks", run: () => setPagesOn((o) => !o) },
    { id: "panel", label: panelOpen ? "Hide suggestions" : "Show suggestions", run: () => setPanelOpen((o) => !o) },
    ...(draft ? [] : [{ id: "chat", label: `Ask Gradis about this ${docKind.noun}`, run: openChat }]),
    { id: "list", label: "All documents", run: () => void go("/documents") },
    { id: "delete", label: deleteLabel, run: () => (unborn ? void doDelete() : setConfirmDelete(true)) },
  ]

  return (
    <div className="flex h-dvh min-w-0 flex-1 flex-col overflow-hidden bg-background text-foreground">
      <div className="flex-none border-b border-border">
        <DocumentHeader
          name={name}
          nameInput={
            <input
              ref={nameRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={commitName}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  e.currentTarget.blur()
                  editor.current?.focus()
                } else if (e.key === "Escape") {
                  setName(sync.title)
                  e.currentTarget.blur()
                }
              }}
              maxLength={isVariant ? 160 : 200}
              aria-label={isVariant ? "Variant name" : "Document name"}
              data-tooltip="Rename"
              style={{ width: `${Math.max(8, name.length + 2)}ch` }}
              className="h-8 min-w-0 max-w-[min(28rem,100%)] truncate rounded-md border border-transparent bg-transparent px-1.5 text-lg leading-tight hover:border-border focus:border-ring focus:outline-none"
            />
          }
          status={<SyncBadge status={sync.status} onRetry={() => void sync.flush()} />}
          target={target}
          folders={source.kind === "doc" && !unborn ? folders.data ?? [] : null}
          folderId={doc.folder_id}
          onMove={(id) => void moveTo(id)}
          draft={!!draft}
          savingVariant={savingVariant}
          onSaveVariant={() => void saveVariant()}
          canExport={!draft && !unborn}
          hasOriginal={doc.has_original}
          views={{ outline: outlineOpen, pages: pagesOn, panel: panelOpen, compare: isVariant ? compare : null }}
          deleteLabel={deleteLabel}
          disabled={!editorReady || compare}
          onBack={() => void go("/documents")}
          actions={{
            exec,
            onLink: () => void openLink(),
            onSuggest: () => editor.current?.openBar(),
            onExport: (c) => void onExport(c),
            onPalette: () => setPaletteOpen(true),
            onTailor: unborn ? null : () => setPickerOpen(true),
            onOpenBase: isVariant ? () => void go(`/documents/${doc.id}`) : null,
            onDelete: () => (unborn ? void doDelete() : setConfirmDelete(true)),
            onRename: () => nameRef.current?.focus(),
            onNew: () => void go(`/documents/new?type=${kindOf(doc.kind)}`),
            onToggleOutline: () => setOutlineOpen((o) => !o),
            onTogglePages: () => setPagesOn((o) => !o),
            onTogglePanel: () => setPanelOpen((o) => !o),
            onToggleCompare: isVariant ? () => setCompare((c) => !c) : null,
          }}
        />

        <DocumentToolbar
          exec={exec}
          onLink={() => void openLink()}
          status={edStatus}
          disabled={!editorReady || compare}
          outlineOpen={outlineOpen}
          onToggleOutline={() => setOutlineOpen((o) => !o)}
          pagesOn={pagesOn}
          onTogglePages={() => setPagesOn((o) => !o)}
          panelOpen={panelOpen}
          onTogglePanel={() => setPanelOpen((o) => !o)}
          pending={pending}
          compare={isVariant ? compare : null}
          onToggleCompare={() => setCompare((c) => !c)}
        />
      </div>

      {versionId && version?.base_updated && !compare && (
        <BaseUpdatedBar
          versionId={versionId}
          noun={docKind.noun}
          busy={lineageBusy}
          onSuggest={() => void suggestBaseChanges()}
          onKeep={() => void keepAsIs()}
        />
      )}

      {sync.status === "conflict" && sync.conflict && (
        <Alert className="m-2 mb-0 rounded-lg">
          <AlertDescription className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="min-w-0 flex-1">
              This was changed somewhere else (another tab or device) since you started editing. Your text is
              kept on this device and hasn't been saved.
            </span>
            <span className="flex shrink-0 gap-2">
              <Button data-tooltip="Replace the saved CV with your local changes" size="sm" onClick={() => sync.resolveConflict("mine")}>Keep mine</Button>
              <Button data-tooltip="Replace your local changes with the version saved on the server" size="sm" variant="outline" onClick={() => sync.resolveConflict("theirs")}>Load the saved version</Button>
            </span>
          </AlertDescription>
        </Alert>
      )}

      <div className="relative flex min-h-0 flex-1">
        {/* Always mounted, so opening and closing can animate its width. */}
        <nav
          aria-label="Outline"
          aria-hidden={!outlineOpen}
          inert={!outlineOpen}
          className={cn(
            // On the canvas's grey, so the page is the one thing that stands out.
            "absolute inset-y-0 left-0 z-20 flex-none overflow-hidden bg-neutral-100 transition-[width,opacity] duration-200 ease-out motion-reduce:transition-none dark:bg-neutral-950 lg:static",
            outlineOpen ? "w-72 opacity-100 shadow-lg lg:shadow-none" : "w-0 opacity-0",
          )}
        >
          <div className="nice-scroll h-full w-72 overflow-y-auto pb-6 pt-4">
            <div className="flex items-center justify-between pb-2 pl-5 pr-2">
              <span className="type-group-label">Outline</span>
              <button type="button" aria-label="Close outline" onClick={() => setOutlineOpen(false)} className="rounded p-1 text-muted-foreground transition-colors duration-150 hover:text-foreground">
                <X className="size-3.5" />
              </button>
            </div>
            {headings.length === 0 && <p className="px-5 py-1 text-xs text-muted-foreground">Headings you add appear here.</p>}
            <ul className="px-3">
              {headings.map((h, i) => {
                const here = h.pos === currentHeading
                return (
                  <li key={`${h.pos}-${i}`}>
                    <button
                      type="button"
                      data-tooltip={h.text}
                      aria-current={here ? "location" : undefined}
                      onClick={() => {
                        if (compare) setCompare(false)
                        window.setTimeout(() => editor.current?.jumpTo(h.pos), 0)
                        if (!wide(1024)) setOutlineOpen(false)
                      }}
                      style={{ paddingLeft: `${8 + (h.level - 1) * 12}px` }}
                      className={cn(
                        "block w-full cursor-pointer truncate rounded-sm py-1 pr-2 text-left text-xs leading-5 transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        h.level <= 2 ? "text-label-secondary" : "text-muted-foreground",
                        h.level === 1 && "font-medium",
                        here && "font-medium text-tint hover:text-tint-hover",
                      )}
                    >
                      {h.text}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        </nav>

        <main
          ref={canvas}
          className="nice-scroll min-w-0 flex-1 overflow-y-auto bg-neutral-100 [--doc-canvas:var(--color-neutral-100)] dark:bg-neutral-950 dark:[--doc-canvas:var(--color-neutral-950)]"
        >
          {compare ? (
            <div className="mx-auto grid max-w-[1400px] gap-4 p-3 sm:p-6 md:grid-cols-2">
              <section className="rounded-sm bg-white p-6 shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
                <div className="mb-3 type-group-label">Base</div>
                <Markdown text={doc.markdown} />
              </section>
              <section className="rounded-sm bg-white p-6 shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
                <div className="mb-3 type-group-label">{sync.title}</div>
                <Markdown text={sync.text} />
              </section>
            </div>
          ) : (
            <div className="sm:px-6 sm:py-8">
              <div
                // A4 at 96dpi with the PDF's margins (18mm, 16mm); full width on a phone. Clipped
                // sideways a pixel out so page breaks also cover its outline.
                data-doc-sheet
                className="mx-auto min-h-full w-full max-w-[794px] overflow-clip [overflow-clip-margin:1px] bg-white text-neutral-900 [--doc-page-x:16px] [--doc-page-y:20px] dark:bg-card dark:text-card-foreground sm:min-h-[1123px] sm:[--doc-page-h:1123px] sm:rounded-sm sm:ring-1 sm:ring-black/10 sm:[--doc-page-x:68px] sm:[--doc-page-y:60px] dark:sm:ring-white/10"
                onMouseDown={(e) => {
                  // A click in the page's empty margin puts the cursor in the text.
                  if (e.target === e.currentTarget) {
                    e.preventDefault()
                    editor.current?.focus()
                  }
                }}
              >
                <React.Suspense
                  fallback={
                    <SkeletonStack className="space-y-3 p-6 sm:p-16" blocks={["h-8 w-1/2", "h-96"]} />
                  }
                >
                  <MarkdownEditor
                    ref={(h) => {
                      editor.current = h
                      if (h && !editorReady) setEditorReady(true)
                    }}
                    value={sync.text}
                    onChange={sync.edit}
                    onStatus={setEdStatus}
                    onBlur={() => void sync.flush()}
                    onLinkRequest={() => void openLink()}
                    onSelectionBar={setBar}
                    placeholder={docKind.placeholder}
                    ariaLabel={`${sync.title} text`}
                  />
                </React.Suspense>
              </div>
            </div>
          )}
        </main>

        {/* Always mounted, like the outline, so opening and closing can animate its width. */}
        <div
          ref={panelBox}
          aria-hidden={!panelOpen}
          inert={!panelOpen}
          style={{ "--panel-w": `${panel.width}px` } as React.CSSProperties}
          className={cn(
            "absolute inset-y-0 right-0 z-20 flex-none overflow-hidden border-border transition-[width,opacity] duration-200 ease-out motion-reduce:transition-none md:relative",
            resizing && "transition-none",
            panelOpen ? "w-[min(var(--panel-w),100%)] border-l opacity-100 shadow-lg md:shadow-none" : "w-0 opacity-0",
          )}
        >
          {/* Its left edge resizes it (from a tablet up; on a phone it's an overlay). */}
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize the suggestions panel"
            aria-valuemin={PANEL_MIN}
            aria-valuemax={panelMax()}
            aria-valuenow={Math.round(panel.width)}
            tabIndex={panelOpen ? 0 : -1}
            onPointerDown={(e) => {
              e.preventDefault()
              e.currentTarget.setPointerCapture(e.pointerId)
              dragWidth.current = panel.width
              setResizing(true)
            }}
            onPointerMove={(e) => {
              const box = panelBox.current
              if (dragWidth.current === null || !box) return
              // Measured from the panel's right edge, so only its left edge moves.
              const right = box.getBoundingClientRect().right
              const w = Math.min(Math.max(right - e.clientX, PANEL_MIN), panelMax())
              dragWidth.current = w
              box.style.setProperty("--panel-w", `${w}px`)
            }}
            onPointerUp={endResize}
            onPointerCancel={endResize}
            onLostPointerCapture={endResize}
            onDoubleClick={() => panel.setWidth(PANEL_MIN)}
            onKeyDown={(e) => {
              const step = e.shiftKey ? 64 : 16
              const to =
                e.key === "ArrowLeft" ? panel.width + step
                : e.key === "ArrowRight" ? panel.width - step
                : e.key === "Home" ? PANEL_MIN
                : e.key === "End" ? panelMax()
                : null
              if (to === null) return
              e.preventDefault()
              panel.setWidth(to)
            }}
            data-tooltip="Drag to resize, double-click to reset"
            className="group/resize absolute inset-y-0 left-0 z-10 hidden w-3 cursor-col-resize touch-none items-center justify-center focus:outline-none md:flex"
          >
            {/* The grip, as on the app's Gradis panel; the edge lights up with it. */}
            <span
              aria-hidden
              className={cn(
                "absolute inset-y-0 left-0 w-px transition-colors duration-150",
                resizing ? "bg-ring" : "bg-transparent group-hover/resize:bg-ring/50 group-focus-visible/resize:bg-ring",
              )}
            />
            <span
              aria-hidden
              className={cn(
                "h-10 w-1 rounded-full transition-colors duration-150",
                resizing ? "bg-ring" : "bg-border group-hover/resize:bg-ring group-focus-visible/resize:bg-ring",
              )}
            />
          </div>
          {draft ? (
            <aside className="flex h-full w-[min(var(--panel-w),100vw)] flex-col bg-neutral-100 dark:bg-neutral-950">
              <div className="flex h-11 flex-none items-center gap-2 pl-4 pr-2">
                <span className="text-sm font-semibold">Suggestions</span>
                <button type="button" aria-label="Close suggestions" onClick={() => setPanelOpen(false)} className="ml-auto rounded-md p-1.5 text-muted-foreground transition-colors duration-150 hover:text-foreground">
                  <X className="size-4" />
                </button>
              </div>
              <div className="p-3">
                <SaveForSuggestions saving={savingVariant} onSave={() => void saveVariant()} />
              </div>
            </aside>
          ) : (
            <SuggestionsPanel
              className="h-full w-[min(var(--panel-w),100vw)] border-l-0"
              suggestions={suggestions.data ?? []}
              requests={requests}
              busyId={busyId}
              activeId={activeId}
              applyingAll={applyingAll}
              onAccept={(s, opts) => void accept(s, opts)}
              onReject={(s) => void reject(s)}
              onLocate={locateSuggestion}
              onApplyAll={() => void applyAll()}
              onRefresh={(s) => void refreshSuggestion(s)}
              onClose={() => setPanelOpen(false)}
              emptyHint={`Select text and choose a change, or press ${shortcutLabel(SHORTCUTS.suggest)}. For changes across the whole ${docKind.noun}, ask Gradis in Chat.`}
              tab={panelTab}
              onTab={setPanelTab}
              chat={
                <div ref={chatPane} className="flex min-h-0 flex-1 flex-col">
                  <GradisChat variant="embedded" />
                </div>
              }
            />
          )}
        </div>
      </div>

      {bar &&
        createPortal(
          <SelectionBar
            key={bar.opened}
            text={bar.text}
            focus={bar.focus}
            saved={!draft}
            tailorFor={tailorFor}
            saving={savingVariant}
            onAsk={(action, instruction) => void requestSuggestion(action, instruction)}
            onChat={draft ? undefined : chatAbout}
            onSave={() => void saveVariant()}
            onClose={() => {
              editor.current?.closeBar()
              editor.current?.focus()
            }}
          />,
          bar.dom,
        )}

      <footer className="flex h-7 flex-none items-center gap-3 border-t border-border px-3 text-xs text-muted-foreground">
        <LengthMeter
          words={wordCount(sync.text)}
          pages={wantLayout ? pages : null}
          limits={limits}
          own={ownLimits}
          inherited={baseLimits}
          canEdit={!draft && !unborn}
          onSave={saveLimits}
        />
        <ChecksButton findings={checks.data?.findings ?? []} onLocate={locateFinding} />
        <span className="ml-auto hidden sm:inline">
          {shortcutLabel(SHORTCUTS.commands)} for commands
        </span>
      </footer>

      <LinkPopover
        request={link}
        onClose={() => {
          setLink(null)
          editor.current?.focus()
        }}
        onApply={(url) => {
          setLink(null)
          exec({ type: "link", url })
        }}
      />

      <TailorPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onPick={(id) => {
          setPickerOpen(false)
          void go(`/documents/${doc.id}?for=${encodeURIComponent(id)}`)
        }}
      />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} commands={commands} />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={draft ? "Discard this variant?" : versionId ? "Delete this variant?" : `Delete this ${docKind.noun}?`}
        description={
          draft
            ? "It was never saved, so it's gone for good. The base stays."
            : versionId
              ? "This removes the tailored variant and its suggestions. The base stays."
              : "This removes it with all its tailored variants, suggestions and any uploaded file. This cannot be undone."
        }
        confirmLabel={draft ? "Discard" : "Delete"}
        onConfirm={() => void doDelete()}
      />

      <Dialog open={leaveTo !== null} onOpenChange={(open) => !open && setLeaveTo(null)}>
        <DialogContent onClose={() => setLeaveTo(null)} className="max-w-md">
          <DialogHeader>
            <DialogTitle>This variant isn&rsquo;t saved</DialogTitle>
            <DialogDescription>
              Save it to your account, keep it as a draft on this device (it stays in your documents here), or discard it.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => leaveDraft("discard")}>Discard</Button>
            <Button data-tooltip="Keep your changes as an unfinished CV variant" variant="outline" onClick={() => leaveDraft("keep")}>Keep as draft</Button>
            <Button data-tooltip="Save this tailored CV as a separate variant" disabled={savingVariant} onClick={() => void saveVariant()}>{savingVariant ? "Saving…" : "Save variant"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function SaveForSuggestions({ saving, onSave }: { saving: boolean; onSave: () => void }) {
  return (
    <div className="rounded-lg bg-fill-quiet p-4 text-center text-sm">
      <p className="font-medium">Save this variant to get suggestions</p>
      <p className="mt-1 text-xs text-muted-foreground">
        It&rsquo;s only on this device for now. Suggestions work on saved documents.
      </p>
      <Button size="sm" className="mt-3 w-full" disabled={saving} onClick={onSave}>
        <Save /> {saving ? "Saving…" : "Save variant"}
      </Button>
    </div>
  )
}

export function WorkspaceSkeleton() {
  return (
    <div className="flex h-dvh min-w-0 flex-1 flex-col bg-background">
      <div className="flex h-14 items-center gap-3 px-3">
        <Skeleton className="size-8 rounded-full" />
        <Skeleton className="h-6 w-48" />
      </div>
      <div className="h-10 border-b border-border" />
      <div className="flex-1 bg-neutral-100 p-8 dark:bg-neutral-950">
        <Skeleton className="mx-auto h-[70vh] max-w-[816px]" />
      </div>
    </div>
  )
}

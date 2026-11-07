import * as React from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import {
  ArrowUpDown,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  CloudOff,
  EllipsisVertical,
  FilePlus2,
  FileUp,
  FolderInput,
  FolderOutput,
  Plus,
  Search,
  Upload,
  X,
} from "lucide-react"
import * as api from "../../lib/api"
import { ApiError } from "../../lib/api"
import { useAuth } from "../../lib/auth"
import { saveFile } from "../../lib/download"
import { formatRelativeDate, utcMs } from "../../lib/format"
import { useCvDocuments, useDocumentFolders } from "../../lib/queries"
import { toastError, toastInfo, toastSuccess } from "../../lib/toast"
import type { CvDocument, CvVersionSummary, DocumentFolder, DocumentKind } from "../../lib/types"
import { cn } from "../../lib/utils"
import { AppLogo } from "../layout/AppLogo"
import { AccountMenu } from "../layout/AccountMenu"
import { GlobalSettingsDialog } from "../dialogs/SettingsDialog"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"
import { Button } from "../ui/button"
import { Skeleton } from "../ui/feedback"
import { EmptyState } from "../feedback/EmptyState"
import { Menu, MenuItem, MenuSeparator } from "../ui/menu"
import { RenameInput } from "../ui/RenameInput"
import { type DocumentDraft, dropAllFor, dropCopy, dropDraft, hasCopy, listDrafts, loadCopy } from "./documentLocal"
import { DocumentThumb, type ThumbSource } from "./DocumentThumb"
import { FolderRail } from "./FolderRail"
import { isKind, KIND, KINDS, kindOf } from "./kinds"
import { TailorPicker } from "./TailorPicker"

const UPLOAD_TYPES = ".docx,.pdf,.md,.markdown,.txt"
/** Whether the template gallery is hidden, remembered on this device. */
const TEMPLATES_KEY = "graduator.documents.templates"

function edited(iso: string | null): string {
  const ms = utcMs(iso)
  if (!iso || Number.isNaN(ms)) return ""
  const rel = formatRelativeDate(iso)
  if (rel === "today") return `Edited ${new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
  return `Edited ${rel}`
}

type Pending =
  | { kind: "doc"; doc: CvDocument }
  | { kind: "version"; version: CvVersionSummary }
  | { kind: "draft"; draft: DocumentDraft }

type Item =
  | { kind: "doc"; doc: CvDocument }
  | { kind: "version"; doc: CvDocument; version: CvVersionSummary }
  | { kind: "draft"; doc: CvDocument; draft: DocumentDraft }

function DocumentKindBadge({ kind }: { kind: DocumentKind }) {
  return (
    <span className="inline-flex shrink-0 rounded-sm bg-fill-quiet px-2 py-0.5 text-xs font-medium text-label-secondary">
      {KIND[kind].short}
    </span>
  )
}

function DocumentCard({
  documentKind,
  to,
  name,
  flag,
  subtitle,
  meta,
  unsynced,
  thumb,
  renaming,
  onRenamed,
  menu,
}: {
  documentKind: DocumentKind
  to: string
  name: string
  flag?: string
  /** Who a variant is for, or what it was made from. */
  subtitle?: string | null
  meta: string
  unsynced?: boolean
  thumb: ThumbSource
  renaming?: boolean
  onRenamed?: (next: string | null) => void
  menu: React.ReactNode
}) {
  const sticky = isSticky(documentKind)
  return (
    <li className="group relative min-w-0">
      <Link
        to={to}
        aria-label={name}
        className="absolute inset-0 z-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      />
      <div
        className={cn(
          "pointer-events-none relative overflow-hidden rounded-md",
          FRAME,
        )}
      >
        <DocumentThumb source={thumb} variant={sticky ? "sticky" : "page"} stickyTone={documentKind === "note" ? "note" : "interest"} compactPage />
        {flag && (
          <span className="g-pill g-pill--caution absolute right-2 top-2 shadow-xs">
            {flag}
          </span>
        )}
      </div>
      <div className="pointer-events-none relative z-1 flex min-w-0 items-start gap-1 pl-0.5 pt-2">
        <div className="min-w-0 flex-1">
          {renaming && onRenamed ? (
            <div className="pointer-events-auto relative z-10">
              <RenameInput value={name} label="New name" selectOnFocus onDone={onRenamed} className="h-7 w-full rounded-md border border-input bg-background px-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-ring" />
            </div>
          ) : (
            <p className="truncate text-sm font-medium leading-6" title={name}>
              {name}
            </p>
          )}
          {subtitle && <p className="truncate text-xs text-label-secondary" title={subtitle}>{subtitle}</p>}
          <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <DocumentKindBadge kind={documentKind} />
            {unsynced && (
              <span data-tooltip="Edits on this device not synced yet" className="pointer-events-auto shrink-0 text-caution">
                <CloudOff className="size-3" aria-label="Not synced yet" />
              </span>
            )}
            <span className="truncate">{meta}</span>
          </p>
        </div>
        <div className="pointer-events-auto relative z-10">{menu}</div>
      </div>
    </li>
  )
}

function TemplateCard({ kind, onSelect }: { kind: DocumentKind; onSelect: (kind: DocumentKind) => void }) {
  const sticky = isSticky(kind)
  return (
    <button
      type="button"
      onClick={() => onSelect(kind)}
      aria-label={`New ${KIND[kind].noun}`}
      className="group flex w-32 shrink-0 cursor-pointer flex-col rounded-lg text-left focus-visible:outline-none"
    >
      <span
        className={cn(
          "relative block overflow-hidden rounded-md group-focus-visible:ring-2 group-focus-visible:ring-ring group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background",
          FRAME,
        )}
      >
        <DocumentThumb source={{ kind: "text", text: KIND[kind].starter }} variant={sticky ? "sticky" : "page"} stickyTone={kind === "note" ? "note" : "interest"} compactPage />
        <span
          aria-hidden
          className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 motion-reduce:transition-none"
        >
          <span className="rounded-full bg-tint p-1.5 text-on-tint shadow-sm">
            <Plus className="size-5" />
          </span>
        </span>
      </span>
      <span className="mt-2 line-clamp-2 px-0.5 text-sm font-medium leading-5 group-hover:text-tint">{KIND[kind].label}</span>
    </button>
  )
}

const FRAME =
  "border border-border shadow-none transition-[box-shadow] duration-200 ease-out group-hover:shadow-sm group-has-[a:focus-visible]:-translate-y-px group-has-[a:focus-visible]:shadow-md group-focus-visible:-translate-y-px group-focus-visible:shadow-md motion-reduce:transition-none motion-reduce:group-hover:translate-y-0"

/** Interest statements and notes are short: they show as sticky notes. */
function isSticky(kind: DocumentKind): boolean {
  return kind === "interest" || kind === "note"
}

const GRID = "grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 sm:gap-x-6 lg:grid-cols-5"

type SortMode = "recent" | "name"

function itemTitle(item: Item): string {
  if (item.kind === "doc") return item.doc.title || `Untitled ${KIND[kindOf(item.doc.kind)].noun}`
  if (item.kind === "draft") return item.draft.name
  return item.version.name
}

function itemEditedAt(item: Item): number {
  if (item.kind === "draft") return item.draft.updatedAt
  return utcMs(item.kind === "doc" ? item.doc.updated_at : item.version.updated_at)
}

function MoreButton({ label }: { label: string }) {
  return (
    <button
      type="button"
      data-tooltip={label}
      aria-label={label}
      className="-mr-1 inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
    >
      <EllipsisVertical className="size-4" />
    </button>
  )
}

/** Emails aren't listed here: they remain Outbox drafts. */
export function DocumentList() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const qc = useQueryClient()
  const { user } = useAuth()
  const userId = user?.id ?? "anon"
  const docs = useCvDocuments()
  const folderQuery = useDocumentFolders()
  const forCandidate = searchParams.get("for")
  const folders = React.useMemo(() => folderQuery.data ?? [], [folderQuery.data])
  const folderParam = searchParams.get("folder")
  const folder = folderParam && folders.some((f) => f.id === folderParam) ? folderParam : null
  const typeParam = searchParams.get("type")
  // Tailoring for a professor starts from a CV.
  const kind: DocumentKind | null = forCandidate ? "cv" : isKind(typeParam) ? typeParam : null

  const [uploading, setUploading] = React.useState(false)
  const [renaming, setRenaming] = React.useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = React.useState<Pending | null>(null)
  const [folderToDelete, setFolderToDelete] = React.useState<DocumentFolder | null>(null)
  const [tailorDoc, setTailorDoc] = React.useState<string | null>(null)
  const [localSeq, setLocalSeq] = React.useState(0)
  const [templatesOpen, setTemplatesOpen] = React.useState(() => {
    try {
      return localStorage.getItem(TEMPLATES_KEY) !== "closed"
    } catch {
      return true
    }
  })
  const [sortMode, setSortMode] = React.useState<SortMode>("recent")
  const fileRef = React.useRef<HTMLInputElement | null>(null)
  const uploadKind = React.useRef<DocumentKind>("cv")

  const all = React.useMemo(() => docs.data ?? [], [docs.data])
  const inFolder = React.useMemo(() => (folder ? all.filter((d) => d.folder_id === folder) : all), [all, folder])
  const list = React.useMemo(() => (kind ? inFolder.filter((d) => kindOf(d.kind) === kind) : inFolder), [inFolder, kind])
  const searchTerm = searchParams.get("q") ?? ""

  function setParam(key: string, value: string | null) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: true },
    )
  }

  // Base document, then its unsaved and saved variants, for each one.
  const items = React.useMemo(() => {
    void localSeq
    const drafts = listDrafts(userId)
    const out: Item[] = []
    for (const doc of list) {
      out.push({ kind: "doc", doc })
      for (const draft of drafts) if (draft.documentId === doc.id) out.push({ kind: "draft", doc, draft })
      for (const version of doc.versions) out.push({ kind: "version", doc, version })
    }
    return out
  }, [list, userId, localSeq])

  const visibleItems = React.useMemo(() => {
    const query = searchTerm.trim().toLocaleLowerCase()
    const matching = items.filter((item) => {
      if (!query) return true
      const kindLabel = KIND[kindOf(item.doc.kind)].label
      const target = item.kind === "draft" ? item.draft.targetLabel : item.kind === "version" ? item.version.target_label : ""
      const folderName = folders.find((entry) => entry.id === item.doc.folder_id)?.name ?? ""
      return [itemTitle(item), item.doc.title, kindLabel, target, folderName]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query)
    })
    return matching.sort((a, b) => {
      if (sortMode === "name") return itemTitle(a).localeCompare(itemTitle(b))
      return itemEditedAt(b) - itemEditedAt(a)
    })
  }, [folders, items, searchTerm, sortMode])

  // Chips count cards: a document and its variants.
  const kindCounts = React.useMemo(() => {
    void localSeq
    const drafts = listDrafts(userId)
    const cards = (d: CvDocument) => 1 + d.versions.length + drafts.filter((x) => x.documentId === d.id).length
    return KINDS.map((k) => ({
      kind: k,
      count: inFolder.filter((d) => kindOf(d.kind) === k).reduce((n, d) => n + cards(d), 0),
    })).filter((c) => c.count > 0 || c.kind === kind)
  }, [inFolder, kind, userId, localSeq])
  const allCount = kindCounts.reduce((n, c) => n + c.count, 0)

  function toggleTemplates() {
    setTemplatesOpen((open) => {
      try {
        localStorage.setItem(TEMPLATES_KEY, open ? "closed" : "open")
      } catch {
        /* storage unavailable: remembered until reload */
      }
      return !open
    })
  }

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["documents"] })
    void qc.invalidateQueries({ queryKey: ["document-folders"] })
  }

  function afterCreate(id: string) {
    refresh()
    navigate(forCandidate ? `/documents/${id}?for=${encodeURIComponent(forCandidate)}` : `/documents/${id}`)
  }

  function upload(k: DocumentKind) {
    uploadKind.current = k
    fileRef.current?.click()
  }

  async function onFile(file: File | undefined) {
    if (!file) return
    setUploading(true)
    const k = uploadKind.current
    try {
      const created = await api.uploadCv(file, { kind: k, folderId: folder })
      toastSuccess(k === "cv" ? "CV read. Check the text: it's your base CV from now on." : `${KIND[k].label} read. Check the text.`)
      afterCreate(created.id)
    } catch (err) {
      toastError(err, "Upload failed")
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  async function startBlank(k: DocumentKind) {
    // Opened unsaved: the first edit creates it, so an untouched template
    // leaves nothing behind. Tailoring needs a saved base CV to fork.
    if (!forCandidate) {
      const params = new URLSearchParams({ type: k })
      if (folder) params.set("folder", folder)
      navigate(`/documents/new?${params}`)
      return
    }
    try {
      const created = await api.createCvFromText({ title: KIND[k].title, markdown: KIND[k].starter, kind: k, folder_id: folder })
      afterCreate(created.id)
    } catch (err) {
      toastError(err)
    }
  }

  async function duplicate(item: Item) {
    try {
      if (item.kind === "doc") {
        const full = await api.getCvDocument(item.doc.id)
        await api.createCvFromText({
          title: `${item.doc.title} (copy)`.slice(0, 200),
          markdown: full.markdown,
          kind: kindOf(item.doc.kind),
          folder_id: item.doc.folder_id,
        })
        toastSuccess(`${item.doc.title} duplicated`)
      } else if (item.kind === "version") {
        const full = await api.getCvVersion(item.version.id)
        await api.createCvVersion(item.doc.id, {
          name: `${item.version.name} (copy)`.slice(0, 160),
          candidate_id: full.candidate_id ?? undefined,
          application_id: full.application_id ?? undefined,
          markdown: full.markdown,
          new: true,
        })
        toastSuccess(`${item.version.name} duplicated`)
      }
      refresh()
    } catch (err) {
      toastError(err, "Couldn't duplicate it")
    }
  }

  async function rename(item: { kind: "doc" | "version"; id: string; revision: number; current: string }, next: string | null) {
    setRenaming(null)
    const clean = next?.trim()
    if (!clean || clean === item.current) return
    try {
      const body = { base_revision: item.revision, title: clean }
      if (item.kind === "doc") await api.saveCvDocument(item.id, body)
      else await api.saveCvVersion(item.id, body)
      refresh()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toastInfo("It changed elsewhere just now. Try renaming again.")
        refresh()
      } else {
        toastError(err, "Rename failed")
      }
    }
  }

  async function moveTo(doc: CvDocument, folderId: string | null) {
    try {
      await api.moveDocument(doc.id, folderId)
      const name = folders.find((f) => f.id === folderId)?.name
      toastSuccess(name ? `${doc.title} moved to ${name}` : `${doc.title} moved out of its folder`)
      refresh()
    } catch (err) {
      toastError(err, "Couldn't move it")
    }
  }


  async function createFolder(name: string) {
    try {
      const f = await api.createDocumentFolder(name)
      refresh()
      setParam("folder", f.id)
    } catch (err) {
      toastError(err, "Couldn't create the folder")
    }
  }

  async function renameFolder(f: DocumentFolder, name: string) {
    try {
      await api.renameDocumentFolder(f.id, name)
      refresh()
    } catch (err) {
      toastError(err, "Rename failed")
    }
  }

  async function moveFolder(f: DocumentFolder, by: -1 | 1) {
    const ids = folders.map((x) => x.id)
    const at = ids.indexOf(f.id)
    const to = at + by
    if (at < 0 || to < 0 || to >= ids.length) return
    ;[ids[at], ids[to]] = [ids[to], ids[at]]
    // Shown in the new order straight away; the server's answer settles it.
    qc.setQueryData(["document-folders"], ids.map((id) => folders.find((x) => x.id === id)))
    try {
      qc.setQueryData(["document-folders"], await api.reorderDocumentFolders(ids))
    } catch (err) {
      toastError(err, "Couldn't reorder the folders")
      refresh()
    }
  }

  async function deleteFolder() {
    const f = folderToDelete
    setFolderToDelete(null)
    if (!f) return
    try {
      await api.deleteDocumentFolder(f.id)
      if (folder === f.id) setParam("folder", null)
      toastSuccess(`${f.name} deleted`)
      refresh()
    } catch (err) {
      toastError(err, "Delete failed")
    }
  }

  async function download(kind: "doc" | "version", id: string, format: api.CvExportFormat | "original") {
    try {
      const file =
        format === "original"
          ? await api.downloadCvOriginal(id)
          : kind === "doc"
            ? await api.exportCvDocument(id, format)
            : await api.exportCvVersion(id, format)
      saveFile(file.blob, file.filename)
    } catch (err) {
      toastError(err, "Download failed")
    }
  }

  async function confirmDelete() {
    const item = pendingDelete
    setPendingDelete(null)
    if (!item) return
    try {
      if (item.kind === "draft") {
        dropDraft(userId, item.draft.id)
        toastSuccess(`${item.draft.name} discarded`)
      } else if (item.kind === "doc") {
        await api.deleteCvDocument(item.doc.id)
        dropAllFor(userId, item.doc.id, item.doc.versions.map((v) => v.id))
        toastSuccess(`${item.doc.title} deleted`)
      } else {
        await api.deleteCvVersion(item.version.id)
        dropCopy(userId, { kind: "version", id: item.version.id })
        toastSuccess(`${item.version.name} deleted`)
      }
      setLocalSeq((n) => n + 1)
      refresh()
    } catch (err) {
      toastError(err, "Delete failed")
    }
  }

  /** The device copy when it has unsynced edits. */
  function savedThumb(kind: "doc" | "version", id: string, stamp: string | null): ThumbSource {
    const copy = loadCopy(userId, { kind, id })
    return copy ? { kind: "text", text: copy.markdown } : { kind, id, stamp }
  }

  function downloads(kind: "doc" | "version", id: string) {
    return [
      <MenuItem key="pdf" onSelect={() => void download(kind, id, "pdf")}>Download PDF</MenuItem>,
      <MenuItem key="docx" onSelect={() => void download(kind, id, "docx")}>Download Word</MenuItem>,
      <MenuItem key="md" onSelect={() => void download(kind, id, "md")}>Download Markdown</MenuItem>,
      <MenuItem key="txt" onSelect={() => void download(kind, id, "txt")}>Download text</MenuItem>,
    ]
  }

  function moves(d: CvDocument) {
    const out = folders
      .filter((f) => f.id !== d.folder_id)
      .map((f) => (
        <MenuItem key={`move-${f.id}`} onSelect={() => void moveTo(d, f.id)}>
          <FolderInput /> <span className="truncate">Move to {f.name}</span>
        </MenuItem>
      ))
    if (d.folder_id) {
      out.push(
        <MenuItem key="move-out" onSelect={() => void moveTo(d, null)}>
          <FolderOutput /> Remove from folder
        </MenuItem>,
      )
    }
    return out
  }

  function card(item: Item) {
    if (item.kind === "doc") {
      const d = item.doc
      const k = kindOf(d.kind)
      const open = forCandidate ? `/documents/${d.id}?for=${encodeURIComponent(forCandidate)}` : `/documents/${d.id}`
      const moveItems = moves(d)
      return (
        <DocumentCard
          key={d.id}
          documentKind={k}
          to={open}
          name={d.title || `Untitled ${KIND[k].noun}`}
          meta={edited(d.updated_at)}
          unsynced={hasCopy(userId, { kind: "doc", id: d.id })}
          thumb={savedThumb("doc", d.id, d.updated_at)}
          renaming={renaming === d.id}
          onRenamed={(next) => void rename({ kind: "doc", id: d.id, revision: d.revision, current: d.title }, next)}
          menu={
            <Menu label={`${d.title} actions`} trigger={<MoreButton label={`More for ${d.title}`} />}>
              <MenuItem onSelect={() => setTailorDoc(d.id)}>Tailor for a professor…</MenuItem>
              <MenuItem onSelect={() => navigate(`/documents/${d.id}?variant=new`)}>New variant</MenuItem>
              <MenuSeparator />
              <MenuItem onSelect={() => setRenaming(d.id)}>Rename</MenuItem>
              <MenuItem onSelect={() => void duplicate(item)}>Duplicate</MenuItem>
              {moveItems.length > 0 ? <MenuSeparator /> : null}
              {moveItems}
              <MenuSeparator />
              {downloads("doc", d.id)}
              {d.has_original ? <MenuItem onSelect={() => void download("doc", d.id, "original")}>Download the uploaded file</MenuItem> : null}
              <MenuSeparator />
              <MenuItem destructive onSelect={() => setPendingDelete({ kind: "doc", doc: d })}>Delete</MenuItem>
            </Menu>
          }
        />
      )
    }
    if (item.kind === "draft") {
      const dr = item.draft
      return (
        <DocumentCard
          key={dr.id}
          documentKind={kindOf(item.doc.kind)}
          to={`/documents/${item.doc.id}?draft=${dr.id}`}
          name={dr.name}
          flag="Unsaved"
          subtitle={dr.targetLabel ? `For ${dr.targetLabel}` : `Variant of ${item.doc.title}`}
          meta="Only on this device"
          thumb={{ kind: "text", text: dr.markdown }}
          menu={
            <Menu label={`${dr.name} actions`} trigger={<MoreButton label={`More for ${dr.name}`} />}>
              <MenuItem destructive onSelect={() => setPendingDelete({ kind: "draft", draft: dr })}>Discard</MenuItem>
            </Menu>
          }
        />
      )
    }
    const v = item.version
    return (
      <DocumentCard
        key={v.id}
        documentKind={kindOf(item.doc.kind)}
        to={`/documents/${item.doc.id}?version=${v.id}`}
        name={v.name}
        flag={v.base_updated ? "Base updated" : undefined}
        subtitle={v.target_label ? `For ${v.target_label}` : `Variant of ${item.doc.title}`}
        meta={edited(v.updated_at)}
        unsynced={hasCopy(userId, { kind: "version", id: v.id })}
        thumb={savedThumb("version", v.id, v.updated_at)}
        renaming={renaming === v.id}
        onRenamed={(next) => void rename({ kind: "version", id: v.id, revision: v.revision, current: v.name }, next)}
        menu={
          <Menu label={`${v.name} actions`} trigger={<MoreButton label={`More for ${v.name}`} />}>
            <MenuItem onSelect={() => setRenaming(v.id)}>Rename</MenuItem>
            <MenuItem onSelect={() => void duplicate(item)}>Duplicate</MenuItem>
            <MenuSeparator />
            {downloads("version", v.id)}
            <MenuSeparator />
            <MenuItem destructive onSelect={() => setPendingDelete({ kind: "version", version: v })}>Delete</MenuItem>
          </Menu>
        }
      />
    )
  }

  const nothingYet = docs.data !== undefined && all.length === 0 && folders.length === 0
  const pendingNoun = pendingDelete?.kind === "doc" ? KIND[kindOf(pendingDelete.doc.kind)].noun : "document"
  const upKind = kind ?? "cv"
  const sortLabel = sortMode === "recent" ? "Last modified" : "Name A–Z"
  const openFolder = folders.find((f) => f.id === folder) ?? null
  return (
    <div className="min-h-dvh bg-(--app-main) text-foreground">
      <header className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto grid min-h-16 w-full max-w-screen-2xl grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 px-3 py-2 sm:h-16 sm:min-h-0 sm:grid-cols-[minmax(0,1fr)_minmax(280px,640px)_minmax(0,1fr)] sm:gap-6 sm:px-6 sm:py-0">
          <div className="flex min-w-0 items-center">
            <Link to="/new" aria-label="Documents, go to new run" className="flex min-w-0 items-center gap-1.5 rounded-md text-label hover:text-tint">
              <AppLogo className="size-8" />
              <h1 className="truncate text-base font-semibold tracking-tight sm:text-lg">Documents</h1>
            </Link>
          </div>
          <label className="g-search col-span-2 row-start-2 w-full min-w-0 sm:col-span-1 sm:row-start-auto">
            <Search className="size-4 shrink-0 text-label-tertiary" aria-hidden />
            <input
              type="search"
              aria-label="Search documents"
              placeholder="Search in Documents"
              value={searchTerm}
              onChange={(event) => setParam("q", event.currentTarget.value || null)}
            />
            {searchTerm && (
              <button
                type="button"
                onClick={() => setParam("q", null)}
                aria-label="Clear search"
                className="inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-full text-label-tertiary hover:bg-fill hover:text-label"
              >
                <X className="size-4" />
              </button>
            )}
          </label>
          <div className="flex shrink-0 items-center justify-end gap-2">
            <AccountMenu compact placement="below" />
          </div>
        </div>
      </header>
      <input
        ref={fileRef}
        type="file"
        accept={UPLOAD_TYPES}
        className="hidden"
        aria-label="Upload a file"
        onChange={(event) => void onFile(event.currentTarget.files?.[0])}
      />

      <section className="bg-muted">
        <div className="mx-auto w-full max-w-7xl px-4 pb-6 pt-5 sm:px-6">
          <div className={cn("flex items-center justify-between gap-3", templatesOpen && "mb-4")}>
            <h2 className="text-sm font-semibold">Start a new document</h2>
            <div className="flex shrink-0 items-center gap-1">
              <Button variant="ghost" size="sm" className="h-9" onClick={() => upload(upKind)} disabled={uploading}>
                <Upload /> {uploading ? "Reading…" : "Upload"}
              </Button>
              <button
                type="button"
                aria-expanded={templatesOpen}
                aria-label={templatesOpen ? "Hide templates" : "Show templates"}
                data-tooltip={templatesOpen ? "Hide templates" : "Show templates"}
                onClick={toggleTemplates}
                className="inline-flex size-9 cursor-pointer items-center justify-center rounded-md text-label-secondary hover:bg-fill-quiet hover:text-label"
              >
                {templatesOpen ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
              </button>
            </div>
          </div>
          {templatesOpen && (
            <div role="group" aria-label="Document templates" className="nice-scroll -mx-1 flex gap-4 overflow-x-auto px-1 pb-1 pt-1">
              {KINDS.map((templateKind) => (
                <TemplateCard key={templateKind} kind={templateKind} onSelect={(selectedKind) => void startBlank(selectedKind)} />
              ))}
            </div>
          )}
        </div>
      </section>

      <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
        {forCandidate && all.length > 0 && (
          <p className="g-banner g-banner--info mb-5">
            Pick the CV to tailor for the professor you chose.
          </p>
        )}

        {!nothingYet && (
          <section aria-labelledby="documents-folders" className="mb-8">
            <h2 id="documents-folders" className="mb-1 text-sm font-semibold">Folders</h2>
            <FolderRail
              folders={folders}
              selected={folder}
              onSelect={(id) => setParam("folder", id)}
              onCreate={(name) => void createFolder(name)}
              onRename={(f, name) => void renameFolder(f, name)}
              onMove={(f, by) => void moveFolder(f, by)}
              onDelete={setFolderToDelete}
            />
          </section>
        )}

        {!nothingYet && (
          <div className="mb-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="flex min-w-0 items-center gap-1.5 text-xl font-semibold tracking-tight">
                {openFolder ? (
                  <>
                    <button
                      type="button"
                      onClick={() => setParam("folder", null)}
                      className="shrink-0 cursor-pointer text-muted-foreground hover:text-foreground"
                    >
                      All documents
                    </button>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="truncate">{openFolder.name}</span>
                  </>
                ) : (
                  "All documents"
                )}
              </h2>
              <Menu
                label="Sort by"
                trigger={
                  <Button variant="ghost" size="sm" aria-label={`Sort by: ${sortLabel}`} className="shrink-0 text-muted-foreground">
                    <ArrowUpDown />
                    <span className="hidden sm:inline">{sortLabel}</span>
                  </Button>
                }
              >
                <MenuItem onSelect={() => setSortMode("recent")}>
                  <span className="min-w-0 flex-1">Last modified</span>
                  {sortMode === "recent" && <Check className="size-4 shrink-0 text-primary" />}
                </MenuItem>
                <MenuItem onSelect={() => setSortMode("name")}>
                  <span className="min-w-0 flex-1">Name A–Z</span>
                  {sortMode === "name" && <Check className="size-4 shrink-0 text-primary" />}
                </MenuItem>
              </Menu>
            </div>
            {!forCandidate && kindCounts.length > 1 && (
              <div role="group" aria-label="Document type" className="g-seg nice-scroll max-w-full overflow-x-auto">
                {[{ kind: null, label: "All", count: allCount }, ...kindCounts.map((c) => ({ ...c, label: KIND[c.kind].plural }))].map(
                  (option) => {
                    const active = kind === option.kind
                    return (
                      <button
                        key={option.kind ?? "all"}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setParam("type", option.kind)}
                        className="shrink-0"
                      >
                        {option.label}
                        <span className="text-xs tabular-nums text-label-tertiary">{option.count}</span>
                      </button>
                    )
                  },
                )}
              </div>
            )}
          </div>
        )}

        {docs.isLoading && (
          <ul aria-hidden className={GRID}>
            {[0, 1, 2, 3, 4].map((i) => (
              <li key={i}>
                <Skeleton className="aspect-4/5 rounded-lg" />
                <Skeleton className="mt-2.5 h-4 w-2/3" />
                <Skeleton className="mt-2 h-3 w-1/2" />
              </li>
            ))}
          </ul>
        )}

        {nothingYet && (
          <div className="mx-auto max-w-lg sm:my-8">
            <EmptyState
              mascot="reading"
              title="Your documents will appear here"
              description={
                forCandidate
                  ? "Add your CV first; then it's tailored for the professor you picked."
                  : "Pick a template above or upload a file. Your CV, statements and notes stay together here."
              }
              action={
                <>
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button onClick={() => upload("cv")} disabled={uploading}>
                      <FileUp /> {uploading ? "Reading…" : "Upload a document"}
                    </Button>
                    <Button variant="secondary" onClick={() => void startBlank("cv")}>
                      <FilePlus2 /> Start a CV
                    </Button>
                  </div>
                  <p className="mt-3 type-caption">Word, PDF, Markdown or plain text</p>
                </>
              }
            />
          </div>
        )}

        {docs.data !== undefined && !nothingYet && visibleItems.length === 0 && (
          <div className="rounded-lg bg-surface px-4 py-10 text-center shadow-sm">
            <p className="text-sm text-label-secondary">
              {searchTerm.trim()
                ? `No documents match “${searchTerm.trim()}”${openFolder ? ` in ${openFolder.name}` : ""}.`
                : kind
                  ? `No ${KIND[kind].plural.toLocaleLowerCase()} ${openFolder ? "in this folder" : "yet"}.`
                  : openFolder
                    ? "Nothing in this folder yet. Move a document here from its menu, or start one above."
                    : "No documents here yet."}
            </p>
            {(searchTerm.trim() || kind) && (
              <button
                type="button"
                onClick={() => {
                  setParam("q", null)
                  if (!forCandidate) setParam("type", null)
                }}
                className="mt-2 cursor-pointer text-sm font-medium text-tint hover:underline"
              >
                {searchTerm.trim() ? "Clear search" : "Show all types"}
              </button>
            )}
          </div>
        )}

        {visibleItems.length > 0 && (
          <ul aria-label={openFolder ? openFolder.name : "All documents"} className={GRID}>
            {visibleItems.map(card)}
          </ul>
        )}
      </main>

      <TailorPicker
        open={tailorDoc !== null}
        onOpenChange={(o) => !o && setTailorDoc(null)}
        onPick={(candidateId) => {
          const id = tailorDoc
          setTailorDoc(null)
          if (id) navigate(`/documents/${id}?for=${encodeURIComponent(candidateId)}`)
        }}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title={
          pendingDelete?.kind === "doc"
            ? `Delete this ${pendingNoun}?`
            : pendingDelete?.kind === "draft"
              ? "Discard this variant?"
              : "Delete this variant?"
        }
        description={
          pendingDelete?.kind === "doc"
            ? "This removes it with all its tailored variants, suggestions and any uploaded file. This cannot be undone."
            : pendingDelete?.kind === "draft"
              ? "It was never saved, so it's gone for good. The base stays."
              : "This removes the tailored variant and its suggestions. The base stays."
        }
        confirmLabel={pendingDelete?.kind === "draft" ? "Discard" : "Delete"}
        onConfirm={() => void confirmDelete()}
      />
      <ConfirmDialog
        open={folderToDelete !== null}
        onOpenChange={(o) => !o && setFolderToDelete(null)}
        title="Delete this folder?"
        description="The documents in it stay, outside any folder."
        confirmLabel="Delete folder"
        onConfirm={() => void deleteFolder()}
      />
      <GlobalSettingsDialog />
    </div>
  )
}

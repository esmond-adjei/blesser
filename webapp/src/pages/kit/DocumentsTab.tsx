import { Select as NativeSelect } from "@blesser/ui"
import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { CloudUpload, Download, FileImage, FileSpreadsheet, FileText, Pencil, RotateCcw, Star, Trash2, X } from "lucide-react"
import { Button, Chip, Field, cn } from "@blesser/ui"
import { SettingsSection } from "../../components/settings/controls"
import { ErrorState } from "../../components/feedback/EmptyState"
import { CheckField, ConfirmDialog, KitSkeleton, SelectField } from "../../components/kit/parts"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../components/ui/dialog"
import { useAutosave } from "../../lib/autosave"
import { formatAgo } from "../../lib/format"
import { DOCUMENT_KINDS, KIT_PITCH, UPLOAD_ACCEPT, formatBytes, guessKind, kindLabel, titleFromFilename, uploadProblem } from "../../lib/kit"
import { deleteDocument, downloadDocument, kitKeys, patchDocument, uploadDocument, useDocuments, useProjects, useUsage } from "../../lib/kitApi"
import type { KitDocument, Project } from "../../lib/kitTypes"
import { toastError, toastSuccess } from "../../lib/toast"

type Upload = { key: string; file: File; progress: number; error: string | null; controller: AbortController; isDefault: boolean }

export function DocumentsTab() {
  return (
    <SettingsSection id="kit-documents" title="Documents" description="CVs, pitch decks, transcripts and certificates, ready to attach when a form asks.">
      <DocumentsBody />
    </SettingsSection>
  )
}

function DocumentsBody() {
  const documents = useDocuments()
  const usage = useUsage()
  const projects = useProjects()
  const client = useQueryClient()
  const [uploads, setUploads] = React.useState<Upload[]>([])
  const [kind, setKind] = React.useState("")
  const [editing, setEditing] = React.useState<KitDocument | null>(null)
  const [removing, setRemoving] = React.useState<KitDocument | null>(null)

  const docs = documents.data ?? []
  const shown = kind ? docs.filter((d) => d.kind === kind) : docs
  const kindsPresent = DOCUMENT_KINDS.filter((k) => docs.some((d) => d.kind === k.value))
  const projectNames = new Map((projects.data ?? []).map((p) => [p.id, p.name]))

  const refresh = React.useCallback(() => {
    void client.invalidateQueries({ queryKey: kitKeys.documents })
  }, [client])

  const start = React.useCallback(
    (upload: Upload) => {
      const patch = (change: Partial<Upload>) => setUploads((list) => list.map((u) => (u.key === upload.key ? { ...u, ...change } : u)))
      uploadDocument(
        { file: upload.file, kind: guessKind(upload.file.name), title: titleFromFilename(upload.file.name), is_default: upload.isDefault || undefined },
        (progress) => patch({ progress }),
        upload.controller.signal,
      )
        .then((doc) => {
          client.setQueryData<KitDocument[]>(kitKeys.documents, (list) => (list ? [doc, ...list.filter((d) => d.id !== doc.id)] : list))
          setUploads((list) => list.filter((u) => u.key !== upload.key))
          refresh()
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === "AbortError") return
          patch({ error: err instanceof Error ? err.message : "Upload failed", progress: 0 })
        })
    },
    [client, refresh],
  )

  const addFiles = (files: FileList | File[]) => {
    let budget = usage.data ? { ...usage.data } : undefined
    const next: Upload[] = []
    const kinds = new Set(docs.map((d) => d.kind))
    for (const file of Array.from(files)) {
      const problem = uploadProblem(file, budget)
      const kind = guessKind(file.name)
      const upload: Upload = { key: `${file.name}-${file.size}-${crypto.randomUUID()}`, file, progress: 0, error: problem, controller: new AbortController(), isDefault: !kinds.has(kind) }
      if (!problem) kinds.add(kind)
      next.push(upload)
      if (!problem && budget) budget = { ...budget, used_bytes: budget.used_bytes + file.size }
    }
    setUploads((list) => [...list, ...next])
    for (const u of next) if (!u.error) start(u)
  }

  const cancel = (u: Upload) => {
    u.controller.abort()
    setUploads((list) => list.filter((x) => x.key !== u.key))
  }

  const retry = (u: Upload) => {
    const fresh = { ...u, error: null, progress: 0, controller: new AbortController() }
    setUploads((list) => list.map((x) => (x.key === u.key ? fresh : x)))
    start(fresh)
  }

  return (
    <div className="space-y-6">
      <StorageMeter used={usage.data?.used_bytes} limit={usage.data?.limit_bytes} />
      <DropZone onFiles={addFiles} />

      {uploads.length ? (
        <ul aria-label="Uploads" className="divide-y divide-separator overflow-hidden rounded-lg border border-separator bg-surface">
          {uploads.map((u) => (
            <li key={u.key} className="flex items-center gap-3 px-4 py-3 sm:px-5">
              <FileIcon name={u.file.name} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-callout text-ink">{u.file.name}</p>
                {u.error ? (
                  <p role="alert" className="text-footnote text-critical">{u.error}</p>
                ) : (
                  <div className="mt-1.5 flex items-center gap-3">
                    <div
                      role="progressbar"
                      aria-label={`Uploading ${u.file.name}`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(u.progress * 100)}
                      className="h-1 flex-1 overflow-hidden rounded-full bg-surface-sunk"
                    >
                      <div className="h-full rounded-full bg-forest transition-[width] duration-200 motion-reduce:transition-none" style={{ width: `${Math.max(3, u.progress * 100)}%` }} />
                    </div>
                    <span className="w-16 shrink-0 text-right text-footnote text-ink-tertiary tabular-nums">
                      {u.progress >= 1 ? "Checking…" : `${Math.round(u.progress * 100)}%`}
                    </span>
                  </div>
                )}
              </div>
              {u.error && !uploadProblem(u.file) ? (
                <Button size="sm" variant="quiet" icon={<RotateCcw />} aria-label={`Retry ${u.file.name}`} onClick={() => retry(u)} className="size-8 [&_svg]:size-4" />
              ) : null}
              <Button
                size="sm"
                variant="quiet"
                icon={<X />}
                aria-label={u.error ? `Dismiss ${u.file.name}` : `Cancel ${u.file.name}`}
                onClick={() => cancel(u)}
                className="size-8 text-ink-tertiary [&_svg]:size-4"
              />
            </li>
          ))}
        </ul>
      ) : null}

      {documents.isLoading ? (
        <KitSkeleton rows={2} />
      ) : documents.isError ? (
        <ErrorState title="Your documents didn't load" description="Check your connection and try again." onRetry={() => void documents.refetch()} />
      ) : docs.length === 0 ? (
        uploads.length ? null : (
          <p className="text-center text-footnote text-ink-secondary">
            Nothing here yet. Start with your CV: most applications ask for one. {KIT_PITCH}
          </p>
        )
      ) : (
        <div className="space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-callout font-semibold text-ink">
              Your files <span className="font-normal text-ink-tertiary tabular-nums">{docs.length}</span>
            </h3>
            {kindsPresent.length > 1 ? (
              <NativeSelect
                aria-label="Show kind"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="select-chevron h-control-sm cursor-pointer appearance-none rounded-sm border border-input-border bg-surface pr-9 pl-3 text-footnote text-ink outline-none transition-[border-color,box-shadow] duration-150 hover:border-input-border-hover focus:border-focus focus:shadow-[0_0_0_3px_var(--focus-soft)]"
              >
                <option value="">All kinds</option>
                {kindsPresent.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
              </NativeSelect>
            ) : null}
          </div>
          <ul className="divide-y divide-separator overflow-hidden rounded-lg border border-separator bg-surface">
            {shown.map((d) => (
              <DocumentRow key={d.id} doc={d} projectNames={projectNames} onEdit={() => setEditing(d)} onDelete={() => setRemoving(d)} />
            ))}
          </ul>
        </div>
      )}

      <EditDialog doc={editing} projects={projects.data ?? []} onClose={() => setEditing(null)} />
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={`Delete ${removing?.title ?? "this file"}?`}
        description="The file is removed from Blesser and unlinked from your projects. This can't be undone."
        confirm="Delete file"
        onConfirm={async () => {
          if (!removing) return
          try {
            await deleteDocument(removing.id)
            client.setQueryData<KitDocument[]>(kitKeys.documents, (list) => list?.filter((d) => d.id !== removing.id))
            refresh()
            toastSuccess("File deleted")
          } catch (err) {
            toastError(err, "Couldn't delete the file")
          }
        }}
      />
    </div>
  )
}

function StorageMeter({ used, limit }: { used?: number; limit?: number }) {
  if (used === undefined || !limit) return <div className="h-9" aria-hidden="true" />
  const fraction = Math.min(1, used / limit)
  const tight = fraction >= 0.9
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-footnote">
        <span id="kit-storage" className="font-semibold text-ink">Storage</span>
        <span className={cn("tabular-nums", tight ? "text-caution" : "text-ink-secondary")}>
          {formatBytes(used)} of {formatBytes(limit)} used
        </span>
      </div>
      <div
        role="meter"
        aria-labelledby="kit-storage"
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={used}
        aria-valuetext={`${formatBytes(used)} of ${formatBytes(limit)} used`}
        className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-sunk"
      >
        <div className={cn("h-full rounded-full", tight ? "bg-caution" : "bg-forest")} style={{ width: `${Math.max(fraction * 100, used ? 1 : 0)}%` }} />
      </div>
    </div>
  )
}

function DropZone({ onFiles }: { onFiles: (files: FileList) => void }) {
  const [over, setOver] = React.useState(false)
  const input = React.useRef<HTMLInputElement | null>(null)
  const depth = React.useRef(0)
  return (
    <div
      onDragEnter={(e) => {
        if (!e.dataTransfer.types.includes("Files")) return
        e.preventDefault()
        depth.current += 1
        setOver(true)
      }}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) e.preventDefault()
      }}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1)
        if (!depth.current) setOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        depth.current = 0
        setOver(false)
        if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files)
      }}
      className={cn(
        "flex flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center transition-colors duration-160",
        over ? "border-forest bg-forest-soft/50" : "border-control-border bg-surface",
      )}
    >
      <span aria-hidden="true" className="grid size-10 place-items-center rounded-full bg-surface-sunk text-ink-secondary">
        <CloudUpload className="size-5" strokeWidth={1.75} />
      </span>
      <p className="text-callout font-medium text-ink">{over ? "Drop to upload" : <><span className="max-sm:hidden">Drag files here</span><span className="sm:hidden">Add your files</span></>}</p>
      <p className="max-w-sm text-footnote text-ink-secondary">PDF, Word, PowerPoint, Excel, CSV or images, up to 15 MB each. Only you can open them.</p>
      <Button size="sm" variant="secondary" className="mt-1" onClick={() => input.current?.click()}>Choose files</Button>
      <input
        ref={input}
        type="file"
        multiple
        accept={UPLOAD_ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          if (e.target.files?.length) onFiles(e.target.files)
          e.target.value = ""
        }}
      />
    </div>
  )
}

function FileIcon({ name, type = "" }: { name: string; type?: string }) {
  const Icon = type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(name) ? FileImage : /\.(xlsx?|csv)$/i.test(name) ? FileSpreadsheet : FileText
  return (
    <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-md bg-surface-sunk text-ink-secondary">
      <Icon className="size-[18px]" strokeWidth={1.75} />
    </span>
  )
}

function DocumentRow({ doc, projectNames, onEdit, onDelete }: { doc: KitDocument; projectNames: Map<string, string>; onEdit: () => void; onDelete: () => void }) {
  const [downloading, setDownloading] = React.useState(false)
  const linked = doc.project_ids.map((id) => projectNames.get(id)).filter(Boolean)
  return (
    <li className="flex items-center gap-3 px-4 py-3 sm:px-5">
      <FileIcon name={doc.filename} type={doc.content_type} />
      <div className="min-w-0 flex-1">
        <p className="flex min-w-0 items-center gap-2">
          <span className="truncate text-callout font-medium text-ink">{doc.title}</span>
          {doc.is_default ? (
            <Chip tone="sun" icon={<Star className="fill-current" />} className="h-5 px-2 max-sm:px-1">
              <span className="max-sm:sr-only">Default</span> <span className="sr-only">{kindLabel(doc.kind)}</span>
            </Chip>
          ) : null}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-3 text-footnote text-ink-tertiary">
          <span className="font-medium text-ink-secondary">{kindLabel(doc.kind)}</span>
          <span className="tabular-nums">{formatBytes(doc.size_bytes)}</span>
          <span className="max-sm:hidden">Added {formatAgo(doc.created_at)}</span>
          {linked.length ? (
            <span className="truncate">{linked.join(", ")}</span>
          ) : null}
        </p>
      </div>
      <div className="flex shrink-0 items-center">
        <Button
          size="sm"
          variant="quiet"
          icon={<Download />}
          aria-label={`Download ${doc.title}`}
          data-tooltip="Download"
          disabled={downloading}
          className="size-8 text-ink-secondary [&_svg]:size-4"
          onClick={async () => {
            setDownloading(true)
            try {
              await downloadDocument(doc)
            } catch (err) {
              toastError(err, "Couldn't download")
            } finally {
              setDownloading(false)
            }
          }}
        />
        <Button size="sm" variant="quiet" icon={<Pencil />} aria-label={`Edit ${doc.title}`} data-tooltip="Rename, retag or link" className="size-8 text-ink-secondary [&_svg]:size-4" onClick={onEdit} />
        <Button size="sm" variant="quiet" icon={<Trash2 />} aria-label={`Delete ${doc.title}`} data-tooltip="Delete" className="size-8 text-ink-secondary hover:text-critical [&_svg]:size-4" onClick={onDelete} />
      </div>
    </li>
  )
}

function EditDialog({ doc, projects, onClose }: { doc: KitDocument | null; projects: Project[]; onClose: () => void }) {
  const [last, setLast] = React.useState(doc)
  if (doc && doc !== last) setLast(doc)
  const shown = doc ?? last
  return (
    <Dialog open={!!doc} onOpenChange={(o) => !o && onClose()}>
      <DialogContent onClose={onClose} className="max-w-md">
        {shown ? <EditForm key={shown.id} doc={shown} projects={projects} onClose={onClose} /> : null}
      </DialogContent>
    </Dialog>
  )
}

function EditForm({ doc, projects, onClose }: { doc: KitDocument; projects: Project[]; onClose: () => void }) {
  const client = useQueryClient()
  const track = useAutosave()
  const [title, setTitle] = React.useState(doc.title)
  const [kind, setKind] = React.useState(doc.kind)
  const [isDefault, setDefault] = React.useState(doc.is_default)
  const [linked, setLinked] = React.useState(doc.project_ids)
  const [busy, setBusy] = React.useState(false)

  return (
    <>
      <DialogHeader>
        <DialogTitle>Edit file</DialogTitle>
        <DialogDescription className="truncate">{doc.filename}</DialogDescription>
      </DialogHeader>
      <DialogBody>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault()
            setBusy(true)
            const saved = await track(patchDocument(doc.id, { title: title.trim() || doc.title, kind, is_default: isDefault, project_ids: linked }))
            setBusy(false)
            if (!saved) return
            client.setQueryData<KitDocument[]>(kitKeys.documents, (list) => list?.map((d) => (d.id === saved.id ? saved : d)))
            void client.invalidateQueries({ queryKey: kitKeys.documents })
            void client.invalidateQueries({ queryKey: kitKeys.projects })
            onClose()
          }}
        >
          <Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required autoFocus />
          <SelectField label="Kind" value={kind} onChange={setKind} options={DOCUMENT_KINDS} />
          <CheckField
            label={`Use as my default ${kindLabel(kind).toLowerCase()}`}
            hint="The extension attaches the default when a form asks for one."
            checked={isDefault}
            onChange={setDefault}
          />
          {projects.length ? (
            <fieldset className="space-y-2">
              <legend className="text-sm leading-5 font-semibold text-ink">Projects</legend>
              {projects.map((p) => (
                <CheckField
                  key={p.id}
                  label={p.name || "Untitled project"}
                  checked={linked.includes(p.id)}
                  onChange={(on) => setLinked(on ? [...linked, p.id] : linked.filter((id) => id !== p.id))}
                />
              ))}
            </fieldset>
          ) : null}
          <div className="flex justify-end gap-2 pt-1">
            <Button size="sm" variant="quiet" onClick={onClose}>Cancel</Button>
            <Button type="submit" size="sm" variant="brand" disabled={busy}>Save</Button>
          </div>
        </form>
      </DialogBody>
    </>
  )
}

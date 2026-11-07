import * as React from "react"
import { BookOpen, CalendarDays, Copy, ExternalLink, Quote, Search, ThumbsDown, ThumbsUp, Users } from "lucide-react"
import { draftEmailText } from "../../lib/drafts"
import type { Paper } from "../../lib/types"
import { cn } from "../../lib/utils"
import { Avatar } from "../ui/avatar"
import { Button, buttonVariants } from "../ui/button"
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { FactList, type Fact } from "./facts"
import { Pager } from "../run/Pager"
import { openAlexUrl } from "../../lib/entities"

/** The full page is unframed; the preview panel keeps the rail's frame. */
export type DetailSize = "page" | "panel"

export function DetailHeader({
  size,
  banner,
  leading,
  title,
  identity,
  actions,
  children,
}: {
  size: DetailSize
  /** Full-width image above the header (schools, applications). */
  banner?: React.ReactNode
  /** Picture beside the title (a person's avatar). */
  leading?: React.ReactNode
  title: React.ReactNode
  /** What the item is: position, school, programme, place... each with an icon. */
  identity?: Array<Fact | null | false | undefined | "" | 0>
  /** Page only: the panel's actions live in its header menu. */
  actions?: React.ReactNode
  /** Status, key figure and facts, stacked under the identity line. */
  children?: React.ReactNode
}) {
  const page = size === "page"
  return (
    <header className="space-y-5">
      {banner}
      <div className={cn("flex flex-wrap items-start", page ? "gap-5" : "gap-4")}>
        {leading}
        <div className="flex min-w-0 flex-1 basis-56 flex-col gap-2">
          <h1 className={cn("wrap-break-word", page ? "type-page-title" : "text-xl font-bold leading-snug tracking-tight")}>
            {title}
          </h1>
          {identity && <FactList facts={identity} />}
          {children}
        </div>
        {page && actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
      </div>
    </header>
  )
}

export function DetailAvatar({ name, src, size }: { name: string; src?: string | null; size: DetailSize }) {
  return <Avatar name={name} src={src} size="lg" className={size === "page" ? "size-30 text-2xl" : undefined} />
}

/** The highlighted half is the status, so detail views need no separate status pill. */
export function ReviewToggle({
  status,
  busy = false,
  onReview,
}: {
  status: string
  busy?: boolean
  onReview: (approved: boolean) => void
}) {
  const approved = status === "approved"
  const rejected = status === "rejected"
  const half = "inline-flex h-8 cursor-pointer items-center gap-1.5 px-2.5 text-compact text-sm font-medium transition-colors disabled:cursor-default disabled:opacity-60"
  return (
    <span role="group" aria-label="Review" className="inline-flex overflow-hidden rounded-md border border-border bg-card">
      <button
        type="button"
        aria-pressed={approved}
        disabled={busy}
        onClick={() => !approved && onReview(true)}
        data-tooltip={approved ? "This professor is already approved" : "Approve this professor for your shortlist"}
        className={cn(half, approved ? "bg-positive-soft text-positive" : "hover:bg-accent")}
      >
        <ThumbsUp className="size-3.5" />
        {approved ? "Approved" : "Approve"}
      </button>
      <button
        type="button"
        aria-pressed={rejected}
        disabled={busy}
        onClick={() => !rejected && onReview(false)}
        data-tooltip={rejected ? "This professor is already rejected" : "Reject this professor from your shortlist"}
        className={cn(
          half,
          "border-l border-border",
          rejected ? "bg-critical-soft text-critical" : "hover:bg-accent",
        )}
      >
        <ThumbsDown className="size-3.5" />
        {rejected && "Rejected"}
      </button>
    </span>
  )
}

/** Clicking opens the full abstract, or calls `onOpen` instead (a hover preview, which a dialog would outlive). */
export function PaperCard({ paper, onOpen }: { paper: Paper; onOpen?: () => void }) {
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => (onOpen ? onOpen() : setOpen(true))}
        className="flex size-full min-h-30 group cursor-pointer gap-3 rounded-xl border border-border bg-card p-3 text-left transition-colors hover:border-foreground/20 hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <div className="recessed-panel relative bg-accent rounded-md shrink-0 w-1/5 h-full overflow-hidden">
          <div className="paper-preview absolute top-1/5 left-1/5 rounded-md bg-card dark:bg-white/50 h-200 w-100 p-2 space-y-2 transform -rotate-3 translate-x-3 group-hover:rotate-0 group-hover:translate-x-0 transition-transform duration-100">
            <div className="w-full h-5 bg-accent/50 rounded-sm"/>
            <div className="w-full h-3 bg-accent/50 rounded-sm"/>
            <div className="w-full h-2 bg-accent/50 rounded-sm"/>
            <div className="w-full h-2 bg-accent/50 rounded-sm"/>
          </div>
        </div>
        <div className="line-clamp-5">
          <h3 className=" leading-snug font-semibold">{paper.title}</h3>
          <FactList size="sm" facts={paperFacts(paper)} />
          {paper.abstract && <p className="text-compact leading-relaxed text-muted-foreground">{paper.abstract}</p>}
        </div>
      </button>
      <PaperDialog paper={paper} open={open} onOpenChange={setOpen} />
    </>
  )
}

/** Publication type, year, citations and how many others wrote it. */
function paperFacts(paper: Paper): Array<Fact | false> {
  const others = paper.coauthors?.length ?? 0
  return [
    !!paper.publication_type && { icon: BookOpen, value: paper.publication_type.replaceAll("-", " ").replace(/^\w/, (c) => c.toUpperCase()) },
    paper.year != null && { icon: CalendarDays, value: String(paper.year) },
    paper.citations != null && { icon: Quote, value: `${paper.citations.toLocaleString()} citation${paper.citations === 1 ? "" : "s"}` },
    others > 0 && { icon: Users, value: `${others} co-author${others === 1 ? "" : "s"}` },
  ]
}

export function PaperDialog({ paper, open, onOpenChange }: { paper: Paper; open: boolean; onOpenChange: (open: boolean) => void }) {
  const scholar = `https://scholar.google.com/scholar?q=${encodeURIComponent(`"${paper.title}"`)}`
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)} className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="leading-snug">{paper.title}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FactList facts={paperFacts(paper)} />
          {paper.abstract ? (
            <p>{paper.abstract}</p>
          ) : (
            <p className="text-muted-foreground">No abstract stored for this paper.</p>
          )}
          {!!paper.coauthors?.length && (
            <section className="space-y-2 pt-2">
              <h3 className="type-group-label">Co-authors</h3>
              <ul className="flex flex-wrap gap-1.5">
                {paper.coauthors.map((a) => {
                  const href = openAlexUrl(a.openalex_id)
                  return (
                    <li key={a.openalex_id ?? a.name}>
                      {href ? (
                        <a href={href} target="_blank" rel="noreferrer" className="inline-flex rounded-full bg-muted px-2.5 py-1 text-xs hover:bg-accent">{a.name}</a>
                      ) : (
                        <span className="inline-flex rounded-full bg-muted px-2.5 py-1 text-xs">{a.name}</span>
                      )}
                    </li>
                  )
                })}
              </ul>
            </section>
          )}
        </DialogBody>
        <DialogFooter className="gap-2">
          <a href={scholar} target="_blank" rel="noreferrer" className={buttonVariants({ size: "sm", variant: "outline" })}>
            <Search /> Find on Google Scholar
          </a>
          {paper.url && (
            <a href={paper.url} target="_blank" rel="noreferrer" className={buttonVariants({ size: "sm" })}>
              <ExternalLink /> Open source
            </a>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const PAPERS_PER_PAGE = 10

export function PaperGrid({ papers, size }: { papers: Paper[]; size: DetailSize }) {
  const [page, setPage] = React.useState(0)
  const pages = Math.ceil(papers.length / PAPERS_PER_PAGE)
  // A shorter list (another professor, a refetch) never strands the view past its end.
  const shown = Math.min(page, Math.max(pages - 1, 0))
  return (
    <div className="space-y-3">
      <ul className={cn("grid gap-3", size === "page" && "sm:grid-cols-2")}>
        {papers.slice(shown * PAPERS_PER_PAGE, (shown + 1) * PAPERS_PER_PAGE).map((p, i) => (
          <li key={`${p.title}-${shown * PAPERS_PER_PAGE + i}`} className="min-w-0">
            <PaperCard paper={p} />
          </li>
        ))}
      </ul>
      <Pager page={shown} pages={pages} total={papers.length} pageSize={PAPERS_PER_PAGE} onPage={setPage} />
    </div>
  )
}

/** With `onSave` it edits in place: subject and body become fields, the footer Cancel / Save. */
export function EmailCard({
  from,
  to,
  date,
  subject,
  body,
  footer,
  clamp = false,
  onSave,
  editing: editingProp,
  onEditingChange,
}: {
  from: { name: string; email?: string | null; avatarUrl?: string | null }
  to: { name: string; email?: string | null }
  date?: string | null
  subject: string
  body: string
  footer?: React.ReactNode
  /** Show the first lines with a fade and a "Show all" toggle. */
  clamp?: boolean
  onSave?: (next: { subject: string; body: string }) => Promise<void>
  editing?: boolean
  onEditingChange?: (editing: boolean) => void
}) {
  const [open, setOpen] = React.useState(!clamp)
  const [editingState, setEditingState] = React.useState(false)
  const editing = editingProp ?? editingState
  const setEditing = React.useCallback(
    (v: boolean) => (onEditingChange ? onEditingChange(v) : setEditingState(v)),
    [onEditingChange],
  )
  const [draftSubject, setDraftSubject] = React.useState(subject)
  const [draftBody, setDraftBody] = React.useState(body)
  const [saving, setSaving] = React.useState(false)
  const cardRef = React.useRef<HTMLElement | null>(null)
  const bodyRef = React.useRef<HTMLTextAreaElement | null>(null)

  // Entering edit mode starts from the saved text.
  const [wasEditing, setWasEditing] = React.useState(editing)
  if (editing !== wasEditing) {
    setWasEditing(editing)
    if (editing) {
      setDraftSubject(subject)
      setDraftBody(body)
    }
  }
  // The body field grows with its text, so editing reads like the email.
  React.useLayoutEffect(() => {
    const el = bodyRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }, [editing, draftBody])

  // Clicking outside ends editing; unsaved edits are dropped, like Cancel.
  React.useEffect(() => {
    if (!editing) return
    const onPointerDown = (e: PointerEvent) => {
      if (cardRef.current?.contains(e.target as Node)) return
      setEditing(false)
    }
    document.addEventListener("pointerdown", onPointerDown)
    return () => document.removeEventListener("pointerdown", onPointerDown)
  }, [editing, setEditing])

  async function save() {
    if (!onSave) return
    setSaving(true)
    try {
      await onSave({ subject: draftSubject, body: draftBody })
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const editable = !!onSave && !editing
  const startEdit = () => editable && setEditing(true)
  const when = date ? new Date(date) : null
  return (
    <article
      ref={cardRef}
      className={cn(
        "overflow-hidden rounded-xl border bg-card transition-colors",
        editing ? "border-ring ring-2 ring-ring/20" : "border-border",
      )}
    >
      <div className="flex items-start gap-3 px-4 pt-4 pb-3">
        <Avatar name={from.name} src={from.avatarUrl} size="md" className="size-10" />
        <div className="min-w-0 flex-1 text-compact">
          <p className="truncate">
            <span className="font-semibold">{from.name}</span>
            {from.email && <span className="text-muted-foreground"> &lt;{from.email}&gt;</span>}
          </p>
          <p className="truncate text-muted-foreground">
            To {to.name}
            {to.email && <> &lt;{to.email}&gt;</>}
          </p>
        </div>
        {when && !isNaN(when.getTime()) && (
          <time dateTime={when.toISOString()} className="shrink-0 type-caption">
            {when.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
          </time>
        )}
      </div>
      {editing ? (
        <div className="px-4 pb-3">
          <input
            value={draftSubject}
            onChange={(e) => setDraftSubject(e.target.value)}
            aria-label="Subject"
            placeholder="Subject"
            className="w-full rounded-md bg-muted/50 px-2 py-1 -mx-2 leading-snug font-semibold tracking-tight outline-none focus:bg-muted"
          />
        </div>
      ) : (
        <h3
          onClick={startEdit}
          data-tooltip={editable ? "Click to edit" : undefined}
          className={cn("px-4 pb-3 leading-snug font-semibold tracking-tight", editable && "cursor-text")}
        >
          {subject || "(no subject)"}
        </h3>
      )}
      <div className="border-t border-border px-4 pt-3 pb-4">
        {editing ? (
          <textarea
            ref={bodyRef}
            value={draftBody}
            onChange={(e) => setDraftBody(e.target.value)}
            aria-label="Body"
            autoFocus
            className="block w-full resize-none overflow-hidden bg-transparent leading-relaxed outline-none"
          />
        ) : (
          <>
            <p
              onClick={startEdit}
              data-tooltip={editable ? "Click to edit" : undefined}
              className={cn(
                editable && "cursor-text rounded-md hover:bg-muted/40",
                !open && "max-h-44 overflow-hidden mask-[linear-gradient(#000_65%,transparent)]",
              )}
            >
              {body}
            </p>
            {clamp && (
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                className="mt-1 cursor-pointer text-xs font-semibold text-primary hover:underline"
              >
                {open ? "Show less" : "Show all"}
              </button>
            )}
          </>
        )}
      </div>
      {editing ? (
        <div className="flex flex-wrap items-center justify-end gap-1.5 border-t border-border bg-muted/40 px-3 py-2.5">
          <span className="mr-auto type-caption">Editing</span>
          <Button size="sm" variant="ghost" disabled={saving} onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button size="sm" disabled={saving || !draftSubject.trim() || !draftBody.trim()} onClick={() => void save()}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      ) : (
        footer && (
          <div className="flex flex-wrap items-center justify-end gap-1.5 border-t border-border bg-muted/40 px-3 py-2.5">{footer}</div>
        )
      )}
    </article>
  )
}

/** Copies a draft's subject and body for the student's own email app. */
export function CopyEmailButton({ subject, body }: { subject: string; body: string }) {
  const [copied, setCopied] = React.useState(false)
  return (
    <Button
      data-tooltip="Copy the subject and message to send in your email app"
      size="sm"
      onClick={() => {
        void navigator.clipboard.writeText(draftEmailText({ subject, body }))
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
    >
      <Copy /> {copied ? "Copied" : "Copy email"}
    </Button>
  )
}

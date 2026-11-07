import * as React from "react"
import { Check, CheckCheck, ChevronRight, LoaderCircle, Pencil, RefreshCw, Sparkles, X } from "lucide-react"
import type { CvSuggestion } from "../../lib/types"
import { cn } from "../../lib/utils"
import { Button } from "../ui/button"
import { LimitNote } from "./LimitsAndChecks"
import { kept, wordDiff } from "./wordDiff"

/** A suggestion on its way: what was asked, for which text. */
export type SuggestionRequest = { id: string; label: string; excerpt: string }

/** Whether a suggestion can no longer be applied as it is: its text was
 * edited since, so applying it would have to guess. */
function isStale(s: CvSuggestion): boolean {
  return s.status === "stale" || (s.status === "pending" && !s.applicable)
}

/** Suggestions are applied (as is or edited) or dismissed; edits adding words absent from
 * the student's documents need confirming. The Chat tab is Gradis, embedded. */
export type PanelTab = "review" | "chat"

export function SuggestionsPanel({
  suggestions,
  requests,
  busyId,
  activeId,
  applyingAll,
  onAccept,
  onReject,
  onLocate,
  onApplyAll,
  onRefresh,
  onClose,
  emptyHint,
  tab = "review",
  onTab,
  chat,
  className,
}: {
  suggestions: CvSuggestion[]
  requests: SuggestionRequest[]
  busyId: string | null
  /** The one whose text is marked in the editor. */
  activeId: string | null
  applyingAll: boolean
  onAccept: (s: CvSuggestion, opts: { replace?: string; confirm: boolean }) => void
  onReject: (s: CvSuggestion) => void
  onLocate: (s: CvSuggestion) => void
  onApplyAll: () => void
  onRefresh: (s: CvSuggestion) => void
  onClose: () => void
  emptyHint: string
  tab?: PanelTab
  onTab?: (tab: PanelTab) => void
  /** The Chat tab's content; without it there's no tab. Kept mounted
   * while Review shows, so the chat survives switching. */
  chat?: React.ReactNode
  className?: string
}) {
  const pending = suggestions.filter((s) => s.status === "pending").reverse()
  // Stale ones stay in view until dismissed or asked for again.
  const stale = suggestions.filter((s) => s.status === "stale" && !s.superseded_by).reverse()
  const done = suggestions
    .filter((s) => s.status !== "pending" && !(s.status === "stale" && !s.superseded_by))
    .slice(-8)
    .reverse()
  const ready = pending.filter((s) => !isStale(s)).length
  // "Apply all" takes the ones that need no check of new words.
  const applicable = pending.filter((s) => s.applicable && !(s.claim_check?.new_terms ?? []).length).length
  const stuck = [...pending.filter(isStale), ...stale]
  const empty = ready === 0 && stuck.length === 0 && requests.length === 0
  return (
    <aside className={cn("flex w-72 flex-none flex-col border-l border-border bg-neutral-100 dark:bg-neutral-950", className)}>
      <div className="flex h-11 flex-none items-center gap-2 pl-4 pr-2">
        {chat ? (
          <div role="tablist" aria-label="Suggestions" className="flex h-full items-stretch gap-4">
            <Tab selected={tab === "review"} onClick={() => onTab?.("review")}>
              Review
              {ready > 0 && <Count n={ready} />}
            </Tab>
            <Tab selected={tab === "chat"} onClick={() => onTab?.("chat")}>
              Chat
            </Tab>
          </div>
        ) : (
          <>
            <span className="text-sm font-semibold">Suggestions</span>
            {ready > 0 && <Count n={ready} />}
          </>
        )}
        <span className="flex-1" />
        {tab === "review" && applicable > 1 && (
          <Button size="sm" variant="ghost" className="h-7 px-2" disabled={applyingAll || busyId !== null} onClick={onApplyAll}>
            <CheckCheck /> {applyingAll ? "Applying…" : "Apply all"}
          </Button>
        )}
        <button
          type="button"
          aria-label="Close suggestions"
          onClick={onClose}
          className="rounded-md p-1.5 text-muted-foreground transition-colors duration-150 hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>
      {chat && <div hidden={tab !== "chat"} className="flex min-h-0 flex-1 flex-col">{chat}</div>}
      <div hidden={tab !== "review"} className="nice-scroll min-h-0 flex-1 space-y-2 overflow-y-auto px-3 pb-6">
        {requests.map((r) => (
          <div key={r.id} role="status" className="rounded-lg bg-background p-3 ring-1 ring-black/5 dark:ring-white/10">
            <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <LoaderCircle className="size-3.5 shrink-0 animate-spin motion-reduce:animate-none" />
              <span className="truncate">{r.label}…</span>
            </p>
            <p className="mt-1.5 line-clamp-2 text-compact leading-snug text-label-tertiary">{r.excerpt}</p>
            <div className="mt-2.5 space-y-1.5" aria-hidden>
              <div className="h-2 w-11/12 animate-pulse rounded-full bg-muted motion-reduce:animate-none" />
              <div className="h-2 w-2/3 animate-pulse rounded-full bg-muted motion-reduce:animate-none" />
            </div>
          </div>
        ))}
        {empty && (
          <div className="flex flex-col items-center px-4 pb-4 pt-10 text-center">
            <span className="mb-3 inline-flex size-10 items-center justify-center rounded-full bg-background text-muted-foreground ring-1 ring-black/5 dark:ring-white/10">
              <Sparkles className="size-4" />
            </span>
            <p className="text-sm font-medium">No suggestions waiting.</p>
            <p className="mt-1 max-w-56 text-xs leading-relaxed text-muted-foreground">{emptyHint}</p>
          </div>
        )}
        {pending
          .filter((s) => !isStale(s))
          .map((s) => (
            <SuggestionCard
              key={s.id}
              suggestion={s}
              busy={busyId === s.id || applyingAll}
              active={activeId === s.id}
              onAccept={onAccept}
              onReject={onReject}
              onLocate={onLocate}
            />
          ))}
        {stuck.length > 0 && (
          <>
            <p className="px-1 pt-3 type-group-label">Out of date</p>
            {stuck.map((s) => (
              <StaleCard key={s.id} suggestion={s} busy={busyId === s.id || applyingAll} onRefresh={onRefresh} onReject={onReject} />
            ))}
          </>
        )}
        {done.length > 0 && (
          <details className="group/history pt-3">
            <summary className="flex cursor-pointer list-none items-center gap-1 px-1 type-group-label transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
              <ChevronRight className="size-3 transition-transform duration-150 group-open/history:rotate-90" />
              History
              <span className="tabular-nums opacity-70">{done.length}</span>
            </summary>
            <ul className="mt-1.5 space-y-0.5">
              {done.map((s) => (
                <li key={s.id} className="flex items-baseline gap-2 px-1 py-1 text-xs text-muted-foreground">
                  <span
                    className={cn(
                      "shrink-0 font-medium",
                      s.status === "accepted" ? "text-positive" : "text-muted-foreground",
                    )}
                  >
                    {s.status === "accepted" ? "applied" : s.status === "rejected" ? "dismissed" : s.superseded_by ? "asked again" : s.status}
                  </span>
                  <span className="line-clamp-1 min-w-0">{s.replace || s.find}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </aside>
  )
}

function Count({ n }: { n: number }) {
  return (
    <span className="min-w-5 rounded-full bg-primary px-1.5 text-center text-xs font-semibold leading-5 text-primary-foreground tabular-nums">
      {n}
    </span>
  )
}

function Tab({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={onClick}
      className={cn(
        "relative inline-flex cursor-pointer items-center gap-1.5 text-sm transition-colors duration-150",
        "after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:rounded-full after:transition-colors",
        selected ? "font-semibold text-foreground after:bg-primary" : "text-muted-foreground hover:text-foreground after:bg-transparent",
      )}
    >
      {children}
    </button>
  )
}

/** The change, marked in place when most of the passage stays, else the
 * passage before and after. Clicking it marks the text in the editor. */
function Change({
  find,
  replace,
  full,
  onLocate,
  editor,
}: {
  find: string
  replace: string
  /** Shown whole; otherwise clamped to a few lines. */
  full: boolean
  onLocate: () => void
  /** In place of the after, while editing it. */
  editor?: React.ReactNode
}) {
  const parts = React.useMemo(() => (editor ? null : wordDiff(find, replace)), [editor, find, replace])
  const clamp = full ? "" : "line-clamp-4"
  const locate = "block w-full cursor-pointer whitespace-pre-wrap rounded-md text-left transition-colors duration-150"
  if (parts && replace && kept(parts) >= 1 / 3)
    return (
      <button type="button" data-tooltip="Show in the text" onClick={onLocate} className={cn(locate, clamp, "-mx-1 px-1 py-0.5 hover:bg-muted/60")}>
        {parts.map((p, i) =>
          p.kind === "same" ? (
            <span key={i}>{p.text}</span>
          ) : p.kind === "del" ? (
            <del key={i} className="rounded-sm bg-critical-soft text-label-secondary decoration-critical">
              {p.text}
            </del>
          ) : (
            <ins
              key={i}
              // Apart from a deletion it follows directly, so "C++" and "MuJoCo" don't read as one word.
              className={cn("rounded-sm bg-positive-soft text-label no-underline", parts[i - 1]?.kind === "del" && "ml-0.5")}
            >
              {p.text}
            </ins>
          ),
        )}
      </button>
    )
  return (
    <div className="space-y-1">
      <button
        type="button"
        data-tooltip="Show in the text"
        onClick={onLocate}
        className={cn(locate, clamp, "border-l-2 border-critical py-0.5 pl-2 text-label-secondary line-through decoration-critical hover:bg-critical-soft")}
      >
        {find}
      </button>
      {editor ?? (
        <button
          type="button"
          data-tooltip="Show in the text"
          onClick={onLocate}
          className={cn(locate, clamp, "border-l-2 border-positive py-0.5 pl-2 hover:bg-positive-soft")}
        >
          {replace || <em className="text-muted-foreground">Remove this text</em>}
        </button>
      )}
    </div>
  )
}

/** A suggestion whose text was edited since: shown, never applied. */
function StaleCard({
  suggestion: s,
  busy,
  onRefresh,
  onReject,
}: {
  suggestion: CvSuggestion
  busy: boolean
  onRefresh: (s: CvSuggestion) => void
  onReject: (s: CvSuggestion) => void
}) {
  return (
    <div aria-disabled className="rounded-lg bg-fill-quiet p-3 text-compact">
      <p className="text-xs text-muted-foreground">The text it changes was edited.</p>
      <p className="mt-1.5 line-clamp-2 leading-snug text-label-tertiary">{s.replace || s.find}</p>
      <div className="mt-2.5 flex items-center gap-1">
        <Button size="sm" variant="outline" className="h-7 bg-background" disabled={busy} onClick={() => onRefresh(s)}>
          <RefreshCw /> Get a fresh suggestion
        </Button>
        <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => onReject(s)}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}

function SuggestionCard({
  suggestion: s,
  busy,
  active,
  onAccept,
  onReject,
  onLocate,
}: {
  suggestion: CvSuggestion
  busy: boolean
  active: boolean
  onAccept: (s: CvSuggestion, opts: { replace?: string; confirm: boolean }) => void
  onReject: (s: CvSuggestion) => void
  onLocate: (s: CvSuggestion) => void
}) {
  const [editing, setEditing] = React.useState(false)
  const [text, setText] = React.useState(s.replace)
  const [confirmed, setConfirmed] = React.useState(false)
  const newTerms = s.claim_check?.new_terms ?? []
  // An edited replacement is re-checked by the server on accept.
  const needsConfirm = !editing && newTerms.length > 0
  const apply = () => onAccept(s, { replace: editing ? text : undefined, confirm: confirmed })
  const toggleEdit = () => {
    setEditing((e) => !e)
    setText(s.replace)
    setConfirmed(false)
  }
  return (
    <article
      aria-current={active || undefined}
      className={cn(
        "rounded-lg bg-background p-3 text-compact leading-relaxed shadow-xs ring-1 transition-shadow duration-150",
        active ? "shadow-md ring-primary/40" : "ring-black/5 hover:shadow-sm dark:ring-white/10",
      )}
    >
      <Change
        find={s.find}
        replace={s.replace}
        full={active || editing}
        onLocate={() => onLocate(s)}
        editor={
          editing ? (
            <textarea
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") toggleEdit()
                else if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !busy) apply()
              }}
              rows={Math.min(8, Math.max(2, text.split("\n").length + 1))}
              className="w-full resize-none rounded-md border border-input bg-background px-2 py-1 text-compact leading-relaxed focus:outline-none focus:ring-2 focus:ring-ring"
              aria-label="Edit the suggested text"
            />
          ) : undefined
        }
      />
      {s.rationale && !editing && <p className="mt-2 text-xs leading-snug text-muted-foreground">{s.rationale}</p>}
      {editing && (
        <label className="mt-2 flex items-start gap-2 type-caption">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5" />
          <span>If my edit adds words my documents don't mention, I've checked they're true.</span>
        </label>
      )}
      <LimitNote check={s.limit_check} />
      {needsConfirm && (
        <label className="mt-2 flex items-start gap-2 rounded-md bg-caution-soft px-2 py-1.5 text-xs text-label">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5" />
          <span>
            Adds words your documents don't mention: <strong>{newTerms.join(", ")}</strong>. I've checked they're true.
          </span>
        </label>
      )}
      <div className="mt-2.5 flex items-center gap-1">
        <Button
          data-tooltip={editing ? "Apply your edit (Ctrl+Enter)" : "Apply this change"}
          size="sm"
          className="h-7 px-2.5"
          disabled={busy || (needsConfirm && !confirmed)}
          onClick={apply}
        >
          <Check /> {editing ? "Apply edit" : "Apply"}
        </Button>
        <Button size="sm" variant="ghost" className="h-7 px-2.5 text-muted-foreground" disabled={busy} onClick={() => (editing ? toggleEdit() : onReject(s))}>
          {editing ? "Cancel" : "Dismiss"}
        </Button>
        {!editing && (
          <button
            type="button"
            data-tooltip="Edit before applying"
            aria-label="Edit before applying"
            disabled={busy}
            onClick={toggleEdit}
            className="ml-auto rounded-md p-1.5 text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground disabled:opacity-40"
          >
            <Pencil className="size-3.5" />
          </button>
        )}
      </div>
    </article>
  )
}

import * as React from "react"
import { Check, Plus, X } from "lucide-react"
import * as api from "../../lib/api"
import { useCvDocuments } from "../../lib/queries"
import { toastError } from "../../lib/toast"
import { Skeleton } from "../ui/feedback"
import type { InterestSuggestions as Result } from "../../lib/types"
import { cn } from "../../lib/utils"

function appendInterest(current: string, phrase: string): string {
  const p = phrase.trim().replace(/[.;]+$/, "")
  const sentence = p.charAt(0).toUpperCase() + p.slice(1) + "."
  const base = current.trim()
  if (!base) return sentence
  return `${base}${/[.!?]$/.test(base) ? "" : "."} ${sentence}`
}

/** Chip widths for the loading skeleton, roughly a real result's shape. */
const SKELETON_CHIPS = ["w-40", "w-28", "w-48", "w-32", "w-36"]

/** Only started by an explicit click, since it sends CV text to the model provider. */
export function InterestSuggestions({
  interest,
  onInterestChange,
  autoStart = false,
  documentId = null,
  onClose,
}: {
  interest: string
  onInterestChange: (next: string) => void
  /** Read the CV at once (the composer's "From my CV" button asked). */
  autoStart?: boolean
  /** The CV to read; null reads the newest few. */
  documentId?: string | null
  onClose?: () => void
}) {
  const docs = useCvDocuments()
  const [result, setResult] = React.useState<Result | null>(null)
  const [loading, setLoading] = React.useState(false)
  const hasDocs = (docs.data ?? []).some((d) => (d.kind ?? "cv") === "cv")
  const controller = React.useRef<AbortController | null>(null)
  const title = docs.data?.find((d) => d.id === documentId)?.title

  async function suggest(ctrl: AbortController) {
    controller.current = ctrl
    setLoading(true)
    try {
      const next = await api.suggestRunInterests(documentId, ctrl.signal)
      if (!ctrl.signal.aborted) setResult(next)
    } catch (err) {
      if (!ctrl.signal.aborted) toastError(err, "Couldn't read your CV")
    } finally {
      if (controller.current === ctrl) {
        controller.current = null
        setLoading(false)
      }
    }
  }

  function cancel() {
    controller.current?.abort()
    controller.current = null
    setLoading(false)
    onClose?.()
  }

  // Leaving the page (or a new "From my CV" press, which remounts this)
  // drops a request still in flight.
  React.useEffect(() => {
    if (!autoStart || !hasDocs) return
    const ctrl = new AbortController()
    void suggest(ctrl)
    return () => ctrl.abort()
    // Started once per mount; `suggest` reads the props it was mounted with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, hasDocs])

  // No CV: nothing to show; the composer's "From my CV" points to the editor.
  if (!hasDocs || (!result && !loading)) return null

  const used = (text: string) => interest.toLowerCase().includes(text.toLowerCase())
  const closeButton = (label: string, onClick: () => void) => (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      data-tooltip={label}
      className="flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
    >
      <X className="size-3.5" />
    </button>
  )

  if (!result) {
    return (
      <div className="space-y-2.5" aria-busy="true">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground" aria-live="polite">
            Reading {title ? <span className="font-medium text-foreground">{title}</span> : "your CV"}…
          </p>
          <button
            type="button"
            onClick={cancel}
            className="h-6 shrink-0 cursor-pointer rounded-md px-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Cancel
          </button>
        </div>
        <ul className="flex flex-wrap gap-1.5" aria-hidden="true">
          {SKELETON_CHIPS.map((w) => (
            <li key={w}>
              <Skeleton className={cn("h-[26px] rounded-full", w)} />
            </li>
          ))}
        </ul>
      </div>
    )
  }

  const dismiss = () => {
    setResult(null)
    onClose?.()
  }

  if (result.suggestions.length === 0) {
    return (
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          Nothing interest-shaped in {title ?? "your CV"}'s research, summary or projects sections yet. Write it in your own words above.
        </p>
        {closeButton("Dismiss", dismiss)}
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          From {result.sources.map((s) => s.title).join(", ")}. Tap to add; edit freely above.
        </p>
        {closeButton("Clear suggestions", dismiss)}
      </div>
      <ul className="flex flex-wrap gap-1.5" aria-label="Interest suggestions">
        {result.suggestions.map((s) => {
          const added = used(s.text)
          return (
            <li key={s.text}>
              <button
                type="button"
                disabled={added}
                onClick={() => onInterestChange(appendInterest(interest, s.text))}
                data-tooltip={`${s.document_title}, ${s.section}\n“${s.evidence}”`}
                className={cn(
                  "inline-flex max-w-full cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-left text-xs transition-colors",
                  added
                    ? "cursor-default border-primary/30 bg-primary/5 text-muted-foreground"
                    : "border-border bg-card hover:border-foreground/20 hover:bg-accent",
                )}
              >
                {added ? <Check className="size-3 shrink-0 text-primary" /> : <Plus className="size-3 shrink-0" />}
                <span className="truncate font-medium">{s.text}</span>
                <span className="shrink-0 text-label-tertiary">{s.section}</span>
              </button>
            </li>
          )
        })}
      </ul>
      {result.method === "heuristic" && (
        <p className="text-xs text-muted-foreground">Lifted directly from your CV text (no model configured).</p>
      )}
    </div>
  )
}

import * as React from "react"
import { ChevronDown } from "lucide-react"
import { Button, Textarea, cn } from "@blesser/ui"
import type { ProblemReport } from "../shared/types"
import { send } from "../shared/ui"

const MAX_NOTE = 2000

/** Opt-in, per report: the member sees what goes (labels and options, never values) before sending. */
export function ReportDialog({ tabId, open, onClose, onSent }: { tabId: number; open: boolean; onClose: () => void; onSent: () => void }) {
  const ref = React.useRef<HTMLDialogElement | null>(null)
  const [preview, setPreview] = React.useState<ProblemReport | null>(null)
  const [note, setNote] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const [sending, setSending] = React.useState(false)
  const [showFields, setShowFields] = React.useState(false)
  const titleId = React.useId()
  const noteId = React.useId()

  React.useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      setPreview(null)
      setError(null)
      setNote("")
      setShowFields(false)
      void send<ProblemReport>({ type: "reportPreview", tabId }).then(setPreview, (err: unknown) =>
        setError(err instanceof Error ? err.message : "Couldn't read this page's fields"),
      )
    } else if (!open && dialog.open) dialog.close()
  }, [open, tabId])

  const submit = async () => {
    if (!preview) return
    setSending(true)
    setError(null)
    try {
      await send({ type: "report", tabId, report: { ...preview, note } })
      onSent()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send the report")
    } finally {
      setSending(false)
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={onClose}
      className="m-auto w-[calc(100%-24px)] max-w-[420px] rounded-lg border border-separator bg-surface p-0 text-ink shadow-elevation-3 backdrop:bg-scrim"
    >
      <form
        method="dialog"
        className="space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <div>
          <h2 id={titleId} className="text-headline text-ink">Report a problem</h2>
          <p className="mt-1 text-footnote text-ink-secondary">
            Tell us what Blesser got wrong on this page. We send the page address and the form's field labels and options so the matcher can be fixed.
            Never what you or Blesser typed.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={noteId} className="text-footnote font-semibold text-ink">What went wrong?</label>
          <Textarea
            id={noteId}
            value={note}
            maxLength={MAX_NOTE}
            onChange={(e) => setNote(e.target.value)}
            rows={4}
            placeholder={'"Country of birth" stayed empty, "Gender" picked the wrong option…'}
            className="min-h-20 px-2.5 text-footnote leading-5"
          />
        </div>
        <div className="rounded-md bg-surface-sunk px-3 py-2">
          {preview ? (
            <>
              <button
                type="button"
                aria-expanded={showFields}
                onClick={() => setShowFields((s) => !s)}
                className="flex w-full items-center gap-1.5 text-left text-footnote text-ink-secondary focus-visible:outline-2 focus-visible:outline-focus"
              >
                <span className="min-w-0 flex-1 truncate">
                  {preview.fields.length} {preview.fields.length === 1 ? "field" : "fields"} from <span className="font-medium text-ink">{preview.page.host}</span>
                </span>
                <span className="shrink-0 font-medium text-link">{showFields ? "Hide" : "See what's sent"}</span>
                <ChevronDown className={cn("size-3.5 shrink-0 text-link transition-transform", showFields && "rotate-180")} aria-hidden="true" />
              </button>
              {showFields ? (
                <ul className="mt-2 max-h-40 space-y-0.5 overflow-y-auto text-[12px] leading-4 text-ink-secondary">
                  {preview.fields.map((f) => (
                    <li key={f.key} className="truncate">
                      {f.label || f.placeholder || f.name || "Unlabelled"} <span className="text-ink-tertiary">({f.type}{f.options.length ? `, ${f.options.length} options` : ""})</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : error ? null : (
            <p className="text-footnote text-ink-tertiary" aria-busy="true">Reading the form…</p>
          )}
        </div>
        {error ? <p role="alert" className="text-footnote text-critical">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="quiet" onClick={onClose} disabled={sending}>Cancel</Button>
          <Button type="submit" size="sm" variant="brand" disabled={!preview || sending || !note.trim()}>
            {sending ? "Sending…" : "Send report"}
          </Button>
        </div>
      </form>
    </dialog>
  )
}

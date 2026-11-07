import * as React from "react"
import { AlertTriangle, ListChecks } from "lucide-react"
import type { CheckFinding, CvLimitCheck, DocumentLimits } from "../../lib/types"
import { cn } from "../../lib/utils"
import { Button } from "../ui/button"
import { Input, Label } from "../ui/input"
import { Popover } from "../ui/popover"

const fmt = (n: number) => n.toLocaleString("en-US")

/** `inherited` is the base's limits, shown for a variant without its own. */
export function LengthMeter({
  words,
  pages,
  limits,
  own,
  inherited,
  canEdit,
  onSave,
}: {
  words: number
  /** From the PDF's layout; null until it's known. */
  pages: number | null
  limits: DocumentLimits
  /** This document's own limits, as the form edits them. */
  own: DocumentLimits
  inherited: DocumentLimits | null
  canEdit: boolean
  onSave: (limits: DocumentLimits) => Promise<boolean>
}) {
  const overWords = limits.word_limit ? words - limits.word_limit : 0
  const overPages = limits.page_limit && pages != null ? pages - limits.page_limit : 0
  const over = overWords > 0 || overPages > 0
  const summary = (
    <>
      {over && <AlertTriangle className="size-3 shrink-0" aria-hidden />}
      <span>
        {fmt(words)}
        {limits.word_limit ? ` / ${fmt(limits.word_limit)}` : ""} words
      </span>
      {(limits.page_limit || pages != null) && pages != null && (
        <span>
          , {pages}
          {limits.page_limit ? ` / ${limits.page_limit}` : ""} {(limits.page_limit ?? pages) === 1 ? "page" : "pages"}
        </span>
      )}
      {over && (
        <span className="hidden sm:inline">
          , over by {overWords > 0 ? `${fmt(overWords)} ${overWords === 1 ? "word" : "words"}` : `${overPages} ${overPages === 1 ? "page" : "pages"}`}
        </span>
      )}
    </>
  )
  const cls = cn("inline-flex items-center gap-1 rounded px-1", over && "font-medium text-caution")
  if (!canEdit) return <span className={cls}>{summary}</span>
  return (
    <Popover
      label="Limits"
      side="top"
      className="sm:w-72"
      trigger={(p) => (
        <button
          {...p}
          type="button"
          aria-label={`${fmt(words)} words${limits.word_limit ? ` of ${fmt(limits.word_limit)}` : ""}. Set limits`}
          className={cn(cls, "-mx-1 hover:bg-accent hover:text-foreground aria-expanded:bg-accent")}
        >
          {summary}
        </button>
      )}
    >
      {(close) => <LimitsForm own={own} inherited={inherited} onSave={onSave} close={close} />}
    </Popover>
  )
}

function LimitsForm({
  own,
  inherited,
  onSave,
  close,
}: {
  own: DocumentLimits
  inherited: DocumentLimits | null
  onSave: (limits: DocumentLimits) => Promise<boolean>
  close: () => void
}) {
  const [words, setWords] = React.useState(own.word_limit?.toString() ?? "")
  const [pages, setPages] = React.useState(own.page_limit?.toString() ?? "")
  const [busy, setBusy] = React.useState(false)
  const num = (v: string) => {
    const n = Number.parseInt(v, 10)
    return Number.isFinite(n) && n > 0 ? n : null
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    const ok = await onSave({ word_limit: num(words), page_limit: num(pages) })
    setBusy(false)
    if (ok) close()
  }
  const hint = (n: number | null | undefined, unit: string) => (inherited && n ? `Base: ${fmt(n)} ${unit}` : "None")
  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-3 p-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label htmlFor="limit-words">Word limit</Label>
          <Input
            id="limit-words"
            type="number"
            inputMode="numeric"
            min={1}
            max={100000}
            value={words}
            placeholder={hint(inherited?.word_limit, "words")}
            onChange={(e) => setWords(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="limit-pages">Page limit</Label>
          <Input
            id="limit-pages"
            type="number"
            inputMode="numeric"
            min={1}
            max={100}
            value={pages}
            placeholder={hint(inherited?.page_limit, "pages")}
            onChange={(e) => setPages(e.target.value)}
          />
        </div>
      </div>
      {inherited && <p className="type-caption">Empty uses the base's limit.</p>}
      <div className="flex justify-end gap-1.5">
        <Button type="button" size="sm" variant="ghost" onClick={close}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={busy}>
          Save
        </Button>
      </div>
    </form>
  )
}

/** Read-only: each finding marks its text when clicked. */
export function ChecksButton({ findings, onLocate }: { findings: CheckFinding[]; onLocate: (f: CheckFinding) => void }) {
  if (findings.length === 0) return null
  return (
    <Popover
      label="Worth a second look"
      side="top"
      className="sm:w-80"
      trigger={(p) => (
        <button
          {...p}
          type="button"
          className="-mx-1 inline-flex items-center gap-1 rounded px-1 hover:bg-accent hover:text-foreground aria-expanded:bg-accent"
        >
          <ListChecks className="size-3.5 shrink-0" aria-hidden />
          {findings.length} to check
        </button>
      )}
    >
      {(close) => (
        <ul className="nice-scroll max-h-80 space-y-0.5 overflow-y-auto p-1.5">
          {findings.map((f, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => {
                  close()
                  onLocate(f)
                }}
                className="block w-full rounded-md px-2 py-1.5 text-left text-compact leading-snug hover:bg-accent"
              >
                {f.message}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Popover>
  )
}

/** What a suggestion does to a limited document, when it's worth saying. */
export function LimitNote({ check }: { check: CvLimitCheck | null }) {
  if (!check) return null
  const byPages = Boolean(
    check.page_limit && check.pages_after != null && !(check.word_limit && check.words_after > check.word_limit),
  )
  const limit = byPages
    ? `${check.pages_after} of ${check.page_limit} pages`
    : `${fmt(check.words_after)} of ${fmt(check.word_limit ?? 0)} words`
  if (check.over_limit)
    return (
      <p className="mt-2 flex items-start gap-1.5 rounded-md bg-caution-soft px-2 py-1.5 text-xs text-label">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>Over the limit: {limit} with this.</span>
      </p>
    )
  if (check.offset) return <p className="mt-2 type-caption">Adds {fmt(check.delta)} words; a cut suggested with it keeps you within the limit.</p>
  return null
}

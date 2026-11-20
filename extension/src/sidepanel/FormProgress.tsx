import * as React from "react"
import { Check, FileDown } from "lucide-react"
import { Button } from "@blesser/ui"
import { countProgress } from "../shared/progress"
import type { FormExport, FormProgress } from "../shared/types"
import { send } from "../shared/ui"
import { buildFormDocx, docxName, DOCX_TYPE } from "./wordExport"

function save(bytes: Uint8Array, name: string) {
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: DOCX_TYPE }))
  const link = document.createElement("a")
  link.href = url
  link.download = name
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

export function FormProgressCard({ tabId, progress, onSaved }: { tabId: number; progress: FormProgress; onSaved: (name: string) => void }) {
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const id = React.useId()
  const count = countProgress(progress)
  if (!count.total) return null

  const percent = Math.round((count.filled / count.total) * 100)
  const left = count.required - count.requiredFilled
  const summary = `${count.filled} of ${count.total} ${count.total === 1 ? "field" : "fields"} filled.`
  const required = !count.required ? "" : left ? ` ${left} required ${left === 1 ? "field" : "fields"} left.` : " All required fields are filled."
  // Before anything is filled every section reads "0 of n"; the list earns its space once there's progress to show.
  const sections = count.sections.length > 1 && count.filled > 0 ? count.sections : []

  const download = async () => {
    setBusy(true)
    setError(null)
    try {
      const form = await send<FormExport>({ type: "exportForm", tabId })
      const name = docxName(form.title)
      save(buildFormDocx(form), name)
      onSaved(name)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't make the Word document")
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="bl-enter space-y-3 rounded-lg border border-separator bg-surface p-3.5 [--i:1]">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={`${id}-title`} className="type-title-3 text-ink">Form progress</h2>
        <p className="text-footnote font-semibold text-ink tabular-nums">{percent}%</p>
      </div>
      <div className="space-y-1.5">
        <div
          role="progressbar"
          aria-labelledby={`${id}-title`}
          aria-valuemin={0}
          aria-valuemax={count.total}
          aria-valuenow={count.filled}
          aria-valuetext={`${count.filled} of ${count.total} fields filled`}
          className="h-1.5 overflow-hidden rounded-full bg-surface-sunk"
        >
          <div className="h-full rounded-full bg-forest transition-[width] duration-500 ease-out motion-reduce:transition-none" style={{ width: `${percent}%` }} />
        </div>
        <p className="text-footnote text-ink-secondary">{summary}{required}</p>
      </div>
      {sections.length ? (
        <ul aria-label="Sections" className="divide-y divide-separator rounded-md bg-surface-sunk">
          {sections.map((section, i) => {
            const done = section.filled === section.total
            return (
              <li key={`${i}:${section.name}`} className="flex items-center justify-between gap-3 px-3 py-1.5 text-footnote">
                <span className="min-w-0 truncate text-ink" title={section.name || "General"}>{section.name || "General"}</span>
                <span className={done ? "flex shrink-0 items-center gap-1 text-positive tabular-nums" : "shrink-0 text-ink-secondary tabular-nums"}>
                  {done ? <Check className="size-3.5" aria-hidden="true" /> : null}
                  {section.filled} of {section.total}
                </span>
              </li>
            )
          })}
        </ul>
      ) : null}
      <Button variant="secondary" size="sm" icon={<FileDown aria-hidden="true" />} className="w-full" disabled={busy} onClick={() => void download()}>
        {busy ? "Preparing…" : "Download as Word"}
      </Button>
      {error ? <p role="alert" className="rounded-md bg-critical-soft px-3 py-2 text-footnote text-critical">{error}</p> : null}
    </section>
  )
}

import * as React from "react"
import { useMutation } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { Button, Input, cn } from "@blesser/ui"
import * as api from "../../lib/api"
import { CATEGORIES, CATEGORY_LABELS } from "../../lib/opportunities"
import { parseSources, type ParsedSource } from "../../lib/parseSources"
import { siteLabel } from "../../lib/scanLog"
import { toastError, toastSuccess } from "../../lib/toast"
import type { OpportunityCategory } from "../../lib/types"

const key = (url: string) => url.replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/+$/, "").toLowerCase()

/** Paste any text with sites in it; review what was found, then add the ones you want. */
export function PasteSources({ existing, slots, category, onAdded }: {
  existing: string[]
  slots: number
  category: OpportunityCategory
  onAdded: () => void
}) {
  const [text, setText] = React.useState("")
  const [edits, setEdits] = React.useState<Record<string, Partial<ParsedSource> & { skip?: boolean }>>({})
  const taken = React.useMemo(() => new Set(existing.map(key)), [existing])
  const parsed = React.useMemo(() => parseSources(text, category), [text, category])
  const fresh = parsed.filter((row) => !taken.has(key(row.url)))
  const rows = fresh.map((row) => ({ ...row, ...edits[key(row.url)] }))
  const picked = rows.filter((row) => !row.skip).slice(0, slots)
  const patch = (url: string, change: Partial<ParsedSource> & { skip?: boolean }) =>
    setEdits((prev) => ({ ...prev, [key(url)]: { ...prev[key(url)], ...change } }))

  const add = useMutation({
    mutationFn: async () => {
      const results = await Promise.allSettled(picked.map((row) => api.addSource({ url: row.url, category: row.category, note: row.note.trim() })))
      const failed = results.flatMap((result, i) => (result.status === "rejected" ? [picked[i].url] : []))
      return { added: picked.length - failed.length, failed }
    },
    onSuccess: ({ added, failed }) => {
      onAdded()
      if (added) toastSuccess(`Added ${added} ${added === 1 ? "source" : "sources"}`)
      if (failed.length) toastError(new Error(`Couldn't add ${failed.map(siteLabel).join(", ")}`), "Some sources weren't added")
      setText("")
      setEdits({})
    },
    onError: (err) => toastError(err, "Couldn't add these sites"),
  })

  return (
    <div className="flex flex-col gap-2 rounded-md bg-surface-sunk p-3">
      <label htmlFor="paste-sources" className="text-caption font-medium text-ink-secondary">
        Paste links or a list <span className="text-ink-tertiary">({slots} {slots === 1 ? "slot" : "slots"} left)</span>
      </label>
      <textarea
        id="paste-sources"
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={!slots}
        maxLength={20000}
        placeholder={"UG scholarships: ug.edu.gh/scholarships\nhttps://foundersfactory.africa/apply - accelerator calls"}
        className="nice-scroll max-h-48 min-h-24 w-full resize-y rounded-md border border-input-border bg-surface px-3 py-2 text-callout text-ink outline-none placeholder:text-ink-tertiary focus-visible:outline-2 focus-visible:outline-focus"
      />
      {text.trim() && !parsed.length ? <p className="text-footnote text-ink-secondary">No sites found in that text.</p> : null}
      {parsed.length && !fresh.length ? <p className="text-footnote text-ink-secondary">Those are already in your sources.</p> : null}
      {rows.length ? (
        <ul aria-label="Sites found" className="flex flex-col gap-2">
          {rows.map((row) => {
            const over = !row.skip && picked.indexOf(row) === -1
            return (
              <li key={key(row.url)} className={cn("flex flex-col gap-1.5 rounded-md bg-surface p-2.5", (row.skip || over) && "opacity-60")}>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`Add ${siteLabel(row.url)}`}
                    checked={!row.skip && !over}
                    disabled={over}
                    onChange={(e) => patch(row.url, { skip: !e.target.checked })}
                    className="size-4 shrink-0 cursor-pointer accent-[var(--forest)]"
                  />
                  <span className="min-w-0 flex-1 truncate text-callout font-semibold text-ink" title={row.url}>{siteLabel(row.url)}</span>
                  <select
                    aria-label={`Audience for ${siteLabel(row.url)}`}
                    value={row.category}
                    onChange={(e) => patch(row.url, { category: e.target.value as OpportunityCategory })}
                    className="h-7 cursor-pointer rounded-full border border-input-border bg-surface px-2 text-footnote text-ink focus-visible:outline-2 focus-visible:outline-focus"
                  >
                    {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
                  </select>
                </div>
                <Input
                  aria-label={`What to look for on ${siteLabel(row.url)}`}
                  value={row.note}
                  onChange={(e) => patch(row.url, { note: e.target.value })}
                  maxLength={500}
                  placeholder="What to look for here (optional)"
                  className="h-control-sm w-full text-footnote"
                 
                />
                {over ? <p className="text-caption text-ink-tertiary">No slot left for this one.</p> : null}
              </li>
            )
          })}
        </ul>
      ) : null}
      <Button
        type="button"
        size="sm"
        variant="primary"
        className="self-end"
        disabled={!picked.length || add.isPending}
        icon={add.isPending ? <Loader2 className="motion-safe:animate-spin" /> : undefined}
        onClick={() => add.mutate()}
      >
        {add.isPending ? "Adding" : picked.length ? `Add ${picked.length} ${picked.length === 1 ? "site" : "sites"}` : "Add sites"}
      </Button>
    </div>
  )
}

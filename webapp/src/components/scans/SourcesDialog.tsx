import * as React from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Pause, Play, RefreshCw, Trash2 } from "lucide-react"
import { Button, Chip, Input, cn } from "@blesser/ui"
import * as api from "../../lib/api"
import { CATEGORIES, CATEGORY_LABELS } from "../../lib/opportunities"
import { siteLabel, sourceStatus } from "../../lib/scanLog"
import { toastError, toastSuccess } from "../../lib/toast"
import type { MemberSource, OpportunityCategory } from "../../lib/types"
import { PasteSources } from "./PasteSources"
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"

const KEY = ["member-sources"]

export function SourcesDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient()
  const sources = useQuery({ queryKey: KEY, queryFn: api.listSources, enabled: open })
  const [url, setUrl] = React.useState("")
  const [note, setNote] = React.useState("")
  const [category, setCategory] = React.useState<OpportunityCategory>("startup")
  const [pasting, setPasting] = React.useState(false)
  const refresh = () => void client.invalidateQueries({ queryKey: KEY })
  const add = useMutation({
    mutationFn: () => api.addSource({ url: url.trim(), category, note: note.trim() }),
    onSuccess: () => {
      setUrl("")
      setNote("")
      refresh()
    },
    onError: (err) => toastError(err, "Couldn't add this site"),
  })
  const check = useMutation({
    mutationFn: api.checkSources,
    onSuccess: () => {
      refresh()
      void client.invalidateQueries({ queryKey: ["scans"] })
      toastSuccess("Checking your sources now")
    },
    onError: (err) => toastError(err, "Couldn't check your sources"),
  })
  const data = sources.data
  const rows = data?.sources ?? []
  const full = !!data && rows.length >= data.max_sources
  const active = rows.some((s) => !s.paused)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>My sources</DialogTitle>
          <p className="text-callout text-ink-secondary">
            Sites Blesser checks for you every {data?.check_days ?? 7} days. New finds show up in your scans, and our team checks them before they go public.
          </p>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-4 pb-2">
          {sources.isLoading ? (
            <p className="flex items-center gap-2 text-footnote text-ink-secondary"><Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" /> Loading</p>
          ) : rows.length ? (
            <ul aria-label="Your sources">
              {rows.map((source) => <SourceRow key={source.id} source={source} onChanged={refresh} />)}
            </ul>
          ) : (
            <p className="text-footnote text-ink-secondary">No sources yet. Add a university, funder or agency page you trust.</p>
          )}
          <div role="tablist" aria-label="How to add" className="flex w-fit rounded-full bg-surface-sunk p-0.5">
            {([["One site", false], ["Paste text", true]] as const).map(([label, value]) => (
              <button
                key={label}
                type="button"
                role="tab"
                aria-selected={pasting === value}
                onClick={() => setPasting(value)}
                className={cn(
                  "h-7 cursor-pointer rounded-full px-3 text-footnote font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-focus",
                  pasting === value ? "bg-surface text-ink shadow-elevation-1" : "text-ink-secondary hover:text-ink",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {pasting ? (
            <PasteSources existing={rows.map((source) => source.url)} slots={Math.max(0, (data?.max_sources ?? 10) - rows.length)} category={category} onAdded={refresh} />
          ) : (
          <form
            onSubmit={(e) => { e.preventDefault(); if (url.trim() && !full) add.mutate() }}
            className="flex flex-col gap-2 rounded-md bg-surface-sunk p-3"
            aria-label="Add a source"
          >
            <label htmlFor="source-url" className="text-caption font-medium text-ink-secondary">
              Add a site <span className="text-ink-tertiary">({rows.length} of {data?.max_sources ?? 10})</span>
            </label>
            <Input
              id="source-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              inputMode="url"
              autoComplete="off"
              maxLength={2000}
              disabled={full}
              placeholder="e.g. ug.edu.gh/scholarships"
              className="h-control-sm w-full text-callout"
            />
            <label htmlFor="source-note" className="sr-only">What to look for on this site</label>
            <Input
              id="source-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              disabled={full}
              placeholder="What to look for here (optional)"
              className="h-control-sm w-full text-callout"
            />
            <div className="flex flex-wrap items-center gap-2">
              <div role="radiogroup" aria-label="Audience" className="flex rounded-full bg-surface p-0.5">
                {CATEGORIES.map((c) => (
                  <button
                    key={c}
                    type="button"
                    role="radio"
                    aria-checked={category === c}
                    onClick={() => setCategory(c)}
                    className={cn(
                      "h-7 cursor-pointer rounded-full px-3 text-footnote font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-focus",
                      category === c ? "bg-surface-sunk text-ink shadow-elevation-1" : "text-ink-secondary hover:text-ink",
                    )}
                  >
                    {CATEGORY_LABELS[c]}
                  </button>
                ))}
              </div>
              <Button type="submit" size="sm" variant="primary" className="ml-auto" disabled={full || !url.trim() || add.isPending}>
                {add.isPending ? "Adding" : "Add site"}
              </Button>
            </div>
            {full ? <p className="text-caption text-ink-tertiary">Remove a source to add another.</p> : null}
          </form>
          )}
        </DialogBody>
        <DialogFooter className="pt-3">
          <Button variant="quiet" onClick={() => onOpenChange(false)}>Close</Button>
          <Button
            variant="secondary"
            icon={check.isPending ? <Loader2 className="motion-safe:animate-spin" /> : <RefreshCw />}
            disabled={!active || check.isPending}
            onClick={() => check.mutate()}
          >
            Check now
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SourceRow({ source, onChanged }: { source: MemberSource; onChanged: () => void }) {
  const toggle = useMutation({
    mutationFn: () => api.updateSource(source.id, { paused: !source.paused }),
    onSuccess: onChanged,
    onError: (err) => toastError(err),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteSource(source.id),
    onSuccess: onChanged,
    onError: (err) => toastError(err),
  })
  const label = siteLabel(source.url)
  return (
    <li className="flex items-start gap-3 border-t border-separator py-2.5 first:border-t-0">
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <a href={source.url} target="_blank" rel="noopener noreferrer nofollow" className="truncate text-callout font-semibold text-ink hover:underline">
            {label}
          </a>
          <Chip tone="neutral">{CATEGORY_LABELS[source.category]}</Chip>
        </div>
        {source.note ? <p className="truncate text-footnote text-ink-secondary" title={source.note}>{source.note}</p> : null}
        <p className="text-caption text-ink-tertiary">
          {sourceStatus(source)}
          {source.last_scan_id ? (
            <>
              {" "}
              <Link to={`/scans/${source.last_scan_id}`} className="text-link hover:underline">See the last check</Link>
            </>
          ) : null}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          size="sm"
          variant="quiet"
          iconOnly
          aria-label={source.paused ? `Resume checks of ${label}` : `Pause checks of ${label}`}
          title={source.paused ? "Resume" : "Pause"}
          icon={source.paused ? <Play /> : <Pause />}
          disabled={toggle.isPending}
          onClick={() => toggle.mutate()}
        />
        <Button
          size="sm"
          variant="quiet"
          iconOnly
          aria-label={`Remove ${label}`}
          title="Remove"
          icon={<Trash2 />}
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        />
      </div>
    </li>
  )
}

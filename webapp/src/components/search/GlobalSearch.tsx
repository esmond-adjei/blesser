import * as React from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Dialog as DialogPrimitive } from "radix-ui"
import { ClipboardList, CornerDownLeft, ListTodo, Radar, Search } from "lucide-react"
import { OpportunityArt, cn } from "@blesser/ui"
import * as api from "../../lib/api"
import { useApplications } from "../../lib/applications"
import { useTodos } from "../../lib/opportunities"
import { CATEGORY_LABELS } from "../../lib/opportunities"
import { NAV_GROUPS } from "../layout/nav"

type Result = { id: string; group: string; label: string; detail?: string; to: string; icon: React.ReactNode }

function useDebounced<T>(value: T, ms = 200): T {
  const [v, setV] = React.useState(value)
  React.useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(t)
  }, [value, ms])
  return v
}

const match = (text: string | null | undefined, q: string) => !!text && text.toLowerCase().includes(q)

/** ⌘K search across pages, the catalog and the member's own applications, to-dos and scans. */
export function GlobalSearch({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const [text, setText] = React.useState("")
  const [active, setActive] = React.useState(0)
  const q = text.trim().toLowerCase()
  const debounced = useDebounced(q)
  const apps = useApplications()
  const todos = useTodos("open", open)
  const scans = useQuery({ queryKey: ["scans"], queryFn: api.listScans, enabled: open })
  const opps = useQuery({
    queryKey: ["search", "opportunities", debounced],
    queryFn: () => api.listOpportunities({ q: debounced }),
    enabled: open && debounced.length >= 2,
    staleTime: 30_000,
  })

  const results: Result[] = []
  const pages = NAV_GROUPS.flatMap((g) => g.items).filter((p) => !q || match(p.label, q))
  results.push(...pages.slice(0, q ? 4 : 8).map((p) => ({ id: `page:${p.to}`, group: "Go to", label: p.label, to: p.to, icon: <p.icon className="size-4" strokeWidth={1.75} /> })))
  if (q) {
    for (const o of (opps.data?.items ?? []).slice(0, 6))
      results.push({ id: `opp:${o.id}`, group: "Opportunities", label: o.title, detail: o.organization ?? undefined, to: `/opportunities/${encodeURIComponent(o.slug || o.id)}`, icon: <OpportunityArt seed={o.slug || o.id} category={o.category} kind={o.kind} shape="square" className="size-5 rounded-[5px]" /> })
    for (const a of (apps.data ?? []).filter((a) => match(a.title, q) || match(a.organization, q)).slice(0, 4))
      results.push({ id: `app:${a.id}`, group: "Applications", label: a.title, detail: a.organization ?? undefined, to: `/applications?open=${a.id}`, icon: <ClipboardList className="size-4" strokeWidth={1.75} /> })
    for (const t of (todos.data ?? []).filter((t) => match(t.title, q)).slice(0, 4))
      results.push({ id: `todo:${t.id}`, group: "To-dos", label: t.title, detail: t.application_label ?? undefined, to: `/calendar?todo=${t.id}`, icon: <ListTodo className="size-4" strokeWidth={1.75} /> })
    for (const s of (scans.data ?? []).filter((s) => match(s.focus, q) || s.categories.some((c) => match(CATEGORY_LABELS[c], q))).slice(0, 3))
      results.push({ id: `scan:${s.id}`, group: "Scans", label: s.focus || s.categories.map((c) => CATEGORY_LABELS[c]).join(", "), detail: s.region, to: `/scans/${s.id}`, icon: <Radar className="size-4" strokeWidth={1.75} /> })
  }

  const go = (r: Result | undefined) => {
    if (!r) return
    onOpenChange(false)
    navigate(r.to)
  }
  const current = Math.min(active, Math.max(results.length - 1, 0))
  const listId = React.useId()

  return (
    <DialogPrimitive.Root open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setText(""); setActive(0) } }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="bl-scrim fixed inset-0 z-50 bg-scrim" />
        <DialogPrimitive.Content
          aria-label="Search"
          className="bl-modal fixed top-[12dvh] left-1/2 z-50 flex max-h-[min(560px,76dvh)] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 flex-col overflow-hidden rounded-lg bg-surface-raised text-ink shadow-elevation-3 focus:outline-none"
        >
          <DialogPrimitive.Title className="sr-only">Search Blesser</DialogPrimitive.Title>
          <div className="flex items-center gap-3 border-b border-separator px-4">
            <Search className="size-4 shrink-0 text-ink-tertiary" aria-hidden="true" />
            <input
              autoFocus
              role="combobox"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={results[current] ? `${listId}-${current}` : undefined}
              placeholder="Search opportunities, applications, to-dos"
              value={text}
              onChange={(e) => { setText(e.target.value); setActive(0) }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, results.length - 1)) }
                else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)) }
                else if (e.key === "Enter") { e.preventDefault(); go(results[current]) }
              }}
              className="h-13 min-w-0 flex-1 bg-transparent text-body outline-none placeholder:text-ink-tertiary"
            />
            <kbd className="rounded-[5px] border border-separator px-1.5 py-0.5 font-sans text-caption text-ink-tertiary max-sm:hidden">Esc</kbd>
          </div>
          <ul id={listId} role="listbox" aria-label="Results" className="nice-scroll min-h-0 flex-1 overflow-y-auto p-2">
            {results.map((r, i) => (
              <React.Fragment key={r.id}>
                {i === 0 || results[i - 1].group !== r.group ? (
                  <li role="presentation" className="px-2 pt-2 pb-1 text-caption text-ink-tertiary first:pt-0.5">{r.group}</li>
                ) : null}
                <li
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === current}
                  onMouseMove={() => setActive(i)}
                  onClick={() => go(r)}
                  className={cn("flex cursor-pointer items-center gap-3 rounded-sm px-2 py-2 text-callout", i === current ? "bg-highlight text-ink" : "text-ink-secondary")}
                >
                  <span className="grid size-5 shrink-0 place-items-center text-ink-tertiary">{r.icon}</span>
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-medium text-ink">{r.label}</span>
                    {r.detail ? <span className="ml-2 text-footnote text-ink-tertiary">{r.detail}</span> : null}
                  </span>
                  {i === current ? <CornerDownLeft className="size-3.5 shrink-0 text-ink-tertiary" aria-hidden="true" /> : null}
                </li>
              </React.Fragment>
            ))}
            {q && !results.length && !opps.isFetching ? (
              <li className="px-2 py-8 text-center text-callout text-ink-secondary">Nothing matches "{text.trim()}".</li>
            ) : null}
            {q.length >= 2 && opps.isFetching ? <li className="px-2 py-2 text-footnote text-ink-tertiary" role="status">Searching the catalog</li> : null}
          </ul>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

/** Opens search on ⌘K or Ctrl+K anywhere in the app. */
export function useSearchShortcut(open: () => void) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        open()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open])
}

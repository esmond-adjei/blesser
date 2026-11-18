import { Checkbox } from "../components/ui/checkbox"
import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import {
  ArrowUpRight,
  Check,
  CalendarPlus,
  Download,
  LayoutGrid,
  List,
  ListPlus,
  Lock,
  PanelRightOpen,
  MapPin,
  Plus,
  Search,
  Share2,
  Sparkles,
} from "lucide-react"
import * as api from "../lib/api"
import {
  CATEGORIES,
  CATEGORY_LABELS,
  KINDS,
  KIND_LABELS,
  countdownFor,
  googleCalendarUrl,
  isCategory,
  isKind,
  useOpportunities,
  useOpportunity,
  useOpportunityFacets,
  useTodoMutations,
  useTrackOpportunity,
  useTrackedOpportunities,
} from "../lib/opportunities"
import { formatAgo } from "../lib/format"
import { useUrlParam } from "../lib/urlParams"
import { toastError, toastSuccess } from "../lib/toast"
import type { Opportunity, OpportunityCategory, OpportunityKind } from "../lib/types"
import {
  Button,
  Countdown,
  Field,
  Input,
  OpportunityArt,
  Select,
  Textarea,
  buttonVariants,
  cn,
} from "@blesser/ui"
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { FilterToggle, PageHeader, Segmented } from "../components/layout/PageHeader"
import { ShareDialog } from "../components/share/ShareDialog"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../components/ui/menu"
import { ScanDialog } from "./Scans"

const SORTS = [
  { value: "deadline", label: "Closing soonest" },
  { value: "new", label: "Newest" },
]

type View = "cards" | "list"
const VIEW_KEY = "blesser.opportunities.view"

function useView(): [View, (view: View) => void] {
  const [view, setView] = React.useState<View>(() => {
    try {
      return localStorage.getItem(VIEW_KEY) === "list" ? "list" : "cards"
    } catch {
      return "cards"
    }
  })
  const choose = React.useCallback((next: View) => {
    setView(next)
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      // Storage can be blocked; the choice still holds for this visit.
    }
  }, [])
  return [view, choose]
}

const GRID = "grid grid-cols-1 gap-5 @xl:grid-cols-2 @4xl:grid-cols-3 @7xl:grid-cols-4 @7xl:gap-6"

export function Opportunities() {
  const [query, setQuery] = useUrlParam("q")
  const [draft, setDraft] = React.useState(query)
  const [categoryParam, setCategory] = useUrlParam("category")
  const [kindParam, setKind] = useUrlParam("kind")
  const [sortParam, setSort] = useUrlParam("sort", "deadline")
  const [soonParam, setSoon] = useUrlParam("soon")
  const [closedParam, setClosed] = useUrlParam("closed")
  const [newParam, setNew] = useUrlParam("new")
  const [openParam, setOpenParam] = useUrlParam("open")
  const category = isCategory(categoryParam) ? categoryParam : undefined
  const kind = isKind(kindParam) ? kindParam : undefined
  const sort = sortParam === "new" ? "new" : "deadline"
  const [view, setView] = useView()

  // Typing waits a beat before it touches the URL and the query; a URL change
  // (back/forward, a link) resets the box during render.
  const [seenQuery, setSeenQuery] = React.useState(query)
  if (seenQuery !== query) {
    setSeenQuery(query)
    setDraft(query)
  }
  React.useEffect(() => {
    if (draft === query) return
    const t = window.setTimeout(() => setQuery(draft.trim()), 300)
    return () => window.clearTimeout(t)
  }, [draft, query, setQuery])

  const list = useOpportunities({
    q: query || undefined,
    category,
    kind,
    sort,
    closing_within: soonParam ? 14 : undefined,
    new: newParam ? true : undefined,
    include_closed: closedParam ? true : undefined,
  })
  const facets = useOpportunityFacets()
  const tracked = useTrackedOpportunities()
  const items = list.data?.pages.flatMap((p) => p.items) ?? []
  const total = list.data?.pages[0]?.total ?? 0
  const counts = new Map(facets.data?.categories.map((c) => [c.key, c.count]))

  const [detail, setDetail] = React.useState<Opportunity | null>(null)
  const linked = useOpportunity(openParam && !detail ? openParam : undefined)
  const shownDetail = detail ?? (openParam ? linked.data ?? null : null)
  const [todoFor, setTodoFor] = React.useState<Opportunity | null>(null)
  const [scanOpen, setScanOpen] = React.useState(false)
  const [submitOpen, setSubmitOpen] = React.useState(false)
  const [shareFor, setShareFor] = React.useState<Opportunity | null>(null)
  const handlers: OpportunityHandlers = { onOpen: setDetail, onTodo: setTodoFor, onShare: setShareFor }
  const filtered = !!(query || category || kind || soonParam || newParam || closedParam)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Opportunities"
        description="Grants, accelerators, fellowships and scholarships open to people in Ghana, checked against each opportunity's own page."
        actions={
          <>
            <Button size="sm" variant="quiet" onClick={() => setSubmitOpen(true)} icon={<Plus />}>
              Share one
            </Button>
            <Button size="sm" variant="primary" onClick={() => setScanOpen(true)} icon={<Sparkles />}>
              Find more
            </Button>
          </>
        }
      />

      <div className="space-y-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            label="Audience"
            value={category ?? ""}
            onChange={(v) => setCategory(v)}
            options={[
              { value: "", label: "All", count: facets.data?.total },
              ...CATEGORIES.map((c) => ({ value: c as string, label: CATEGORY_LABELS[c], count: counts.get(c) ?? 0 })),
            ]}
          />
          <div className="relative min-w-[200px] flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-tertiary" />
            <Input
              type="search"
              aria-label="Search opportunities"
              placeholder="Search by name, funder, sector…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="h-control-sm w-full pl-9 text-callout"
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            aria-label="Kind"
            className="h-control-sm w-auto min-w-[140px] text-footnote"
            value={kind ?? ""}
            onChange={(e) => setKind(e.target.value)}
          >
            <option value="">All kinds</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Sort"
            className="h-control-sm w-auto min-w-[150px] text-footnote"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
          <FilterToggle pressed={!!newParam} onChange={(on) => setNew(on ? "1" : "")}>
            New this week
          </FilterToggle>
          <FilterToggle pressed={!!soonParam} onChange={(on) => setSoon(on ? "1" : "")}>
            Closing in 2 weeks
          </FilterToggle>
          <FilterToggle pressed={!!closedParam} onChange={(on) => setClosed(on ? "1" : "")}>
            Include closed
          </FilterToggle>
          <span className="ml-auto text-footnote text-ink-tertiary" aria-live="polite">
            {list.isSuccess ? `${total} ${total === 1 ? "result" : "results"}` : ""}
          </span>
          <Segmented
            label="View"
            value={view}
            onChange={setView}
            options={[
              { value: "cards", label: "Cards", icon: <LayoutGrid aria-hidden="true" /> },
              { value: "list", label: "List", icon: <List aria-hidden="true" /> },
            ]}
          />
        </div>
      </div>

      {list.isLoading && view === "cards" ? (
        <div className="@container">
          <div className={GRID}>
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className="overflow-hidden rounded-lg border border-separator bg-surface">
                <div className="aspect-[16/7] animate-pulse bg-surface-sunk motion-reduce:animate-none" />
                <div className="space-y-3 p-5">
                  <div className="h-3 w-1/3 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" />
                  <div className="h-4 w-3/4 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" />
                  <div className="h-3 w-1/2 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : list.isLoading ? (
        <div className="divide-y divide-separator rounded-lg border border-separator bg-surface">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="h-[72px] px-4 py-3">
              <div className="h-4 w-1/2 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" />
              <div className="mt-2 h-3 w-1/3 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" />
            </div>
          ))}
        </div>
      ) : list.isError ? (
        <ErrorState title="Opportunities didn't load" description="Check your connection and try again." onRetry={() => void list.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          title={filtered ? "Nothing matches these filters" : "No opportunities yet"}
          description="Send agents to look for new ones, or share one you know about."
          action={
            <Button size="sm" onClick={() => setScanOpen(true)} icon={<Sparkles />}>
              Find more
            </Button>
          }
        />
      ) : (
        <>
          {view === "cards" ? (
            <div className="@container" key="cards">
              <ul className={GRID}>
                {items.map((opp, i) => (
                  <OpportunityTile key={opp.id} index={i} opp={opp} applicationId={tracked.data?.[opp.id]} {...handlers} />
                ))}
              </ul>
            </div>
          ) : (
            <ul className="divide-y divide-separator rounded-lg border border-separator bg-surface">
              {items.map((opp, i) => (
                <OpportunityRow key={opp.id} index={i} opp={opp} applicationId={tracked.data?.[opp.id]} {...handlers} />
              ))}
            </ul>
          )}
          {list.hasNextPage ? (
            <div className="flex justify-center">
              <Button size="sm" onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage}>
                {list.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            </div>
          ) : null}
        </>
      )}

      <OpportunityDetail
        opp={shownDetail}
        applicationId={shownDetail ? tracked.data?.[shownDetail.id] : undefined}
        onClose={() => {
          setDetail(null)
          if (openParam) setOpenParam("")
        }}
        onTodo={setTodoFor}
        onShare={setShareFor}
      />
      <TodoDialog opp={todoFor} onClose={() => setTodoFor(null)} />
      <ScanDialog open={scanOpen} onOpenChange={setScanOpen} />
      <SubmitDialog open={submitOpen} onOpenChange={setSubmitOpen} />
      <ShareDialog opp={shareFor} onClose={() => setShareFor(null)} />
    </div>
  )
}

function Markers({ opp, members = true }: { opp: Opportunity; members?: boolean }) {
  return (
    <>
      {opp.is_new ? (
        <span className="inline-flex items-center gap-1 text-caption text-sun-ink">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-sun" />
          New
        </span>
      ) : null}
      {members && opp.audience === "members" ? (
        <span className="inline-flex items-center gap-1 text-caption text-ink-tertiary">
          <Lock aria-hidden="true" className="size-3" />
          Members only
        </span>
      ) : null}
    </>
  )
}

function OpportunityMeta({ opp }: { opp: Opportunity }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-footnote text-ink-secondary">
      <Countdown {...countdownFor(opp)} />
      <span>{KIND_LABELS[opp.kind] ?? opp.kind}</span>
      <span>{CATEGORY_LABELS[opp.category] ?? opp.category}</span>
      {opp.location ? (
        <span className="inline-flex items-center gap-1">
          <MapPin aria-hidden="true" className="size-3.5 text-ink-tertiary" />
          {opp.location}
        </span>
      ) : null}
      <Markers opp={opp} />
    </div>
  )
}

const FOUND_BY: Record<Opportunity["found_by"], string> = {
  agent: "Found by an agent",
  community: "Shared by the community",
  staff: "Added by the Blesser team",
}

function useTrack(opp: Opportunity, applicationId: string | undefined) {
  const track = useTrackOpportunity()
  const navigate = useNavigate()
  return {
    pending: track.isPending,
    onTrack: () => {
      if (applicationId) return navigate("/applications")
      track.mutate(opp.id, {
        onSuccess: () => toastSuccess("Tracked. Deadline reminders are on."),
        onError: (err) => toastError(err, "That didn't track. Try again."),
      })
    },
  }
}

function TrackButton({ opp, applicationId, className }: { opp: Opportunity; applicationId: string | undefined; className?: string }) {
  const { pending, onTrack } = useTrack(opp, applicationId)
  if (applicationId)
    return (
      <Link to="/applications" className={cn(buttonVariants({ size: "sm", variant: "quiet" }), "text-link", className)}>
        <Check /> Tracking
      </Link>
    )
  return (
    <Button size="sm" variant="primary" disabled={pending} onClick={onTrack} icon={<Plus />} className={className}>
      Track
    </Button>
  )
}

export interface OpportunityHandlers {
  onOpen?: (opp: Opportunity) => void
  onTodo: (opp: Opportunity) => void
  onShare: (opp: Opportunity) => void
}

/** Everything but Track, which each surface shows as its own button. */
function secondaryActions(opp: Opportunity, { onOpen, onTodo, onShare }: OpportunityHandlers, withOfficial = true): MenuAction[] {
  const google = googleCalendarUrl(opp)
  const official = withOfficial ? opp.link || opp.source_url : ""
  const actions: MenuAction[] = []
  if (onOpen) actions.push({ label: "Open details", icon: <PanelRightOpen />, onSelect: () => onOpen(opp) }, { kind: "separator" })
  actions.push({ label: "Add a to-do", icon: <ListPlus />, onSelect: () => onTodo(opp) })
  if (google) {
    actions.push(
      { label: "Add to Google Calendar", icon: <CalendarPlus />, href: google },
      {
        label: "Download .ics",
        icon: <Download />,
        onSelect: () => void api.downloadOpportunityIcs(opp.id).catch((err) => toastError(err, "The .ics didn't download")),
      },
    )
  }
  actions.push({ label: "Share", icon: <Share2 />, onSelect: () => onShare(opp) })
  if (official) actions.push({ kind: "separator" }, { label: "Official page", icon: <ArrowUpRight />, href: official })
  return actions
}

interface ItemProps extends OpportunityHandlers {
  opp: Opportunity
  applicationId: string | undefined
  index: number
}

function Art({ opp, shape, className }: { opp: Opportunity; shape: "banner" | "square"; className?: string }) {
  return <OpportunityArt seed={opp.slug || opp.id} category={opp.category} kind={opp.kind} shape={shape} className={className} />
}

function OpportunityTile({ opp, applicationId, index, ...handlers }: ItemProps) {
  const meta = [KIND_LABELS[opp.kind] ?? opp.kind, CATEGORY_LABELS[opp.category]].filter(Boolean)
  const actions = secondaryActions(opp, handlers)
  const open = () => handlers.onOpen?.(opp)
  return (
    <ActionContextMenu actions={actions}>
      <li
        style={{ "--i": index } as React.CSSProperties}
        className="bl-enter bl-lift flex min-w-0 flex-col overflow-hidden rounded-lg border border-separator bg-surface hover:shadow-elevation-1"
      >
        <div aria-hidden="true" onClick={open} className="cursor-pointer">
          <Art opp={opp} shape="banner" />
        </div>
        <div className="flex flex-1 flex-col p-5 sm:p-6">
          {opp.organization ? <p className="truncate text-footnote text-ink-tertiary">{opp.organization}</p> : null}
          <h3 className="mt-1.5">
            <button type="button" onClick={open} className="line-clamp-2 cursor-pointer text-left text-headline text-balance text-ink hover:underline">
              {opp.title}
            </button>
          </h3>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-footnote text-ink-secondary">
            <span>{meta.join(", ")}</span>
            <Markers opp={opp} members={false} />
          </div>
          {opp.benefits ? <p className="mt-4 line-clamp-2 text-callout text-ink">{opp.benefits}</p> : null}
          <div className="mt-auto flex items-center gap-2 pt-5">
            <Countdown variant="text" {...countdownFor(opp)} className="mr-auto" />
            <TrackButton opp={opp} applicationId={applicationId} />
            <ActionMenuButton actions={actions} label={`More for ${opp.title}`} />
          </div>
        </div>
      </li>
    </ActionContextMenu>
  )
}

function OpportunityRow({ opp, applicationId, index, ...handlers }: ItemProps) {
  const meta = [opp.organization, KIND_LABELS[opp.kind] ?? opp.kind, CATEGORY_LABELS[opp.category]].filter(Boolean)
  const actions = secondaryActions(opp, handlers)
  const open = () => handlers.onOpen?.(opp)
  return (
    <ActionContextMenu actions={actions}>
      <li
        style={{ "--i": index } as React.CSSProperties}
        className="bl-enter flex items-center gap-3 px-3 py-3 transition-colors hover:bg-highlight/50 data-[state=open]:bg-highlight/50 sm:gap-4 sm:px-4"
      >
        <div aria-hidden="true" onClick={open} className="shrink-0 cursor-pointer">
          <Art opp={opp} shape="square" className="size-10 rounded-md sm:size-11" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <button type="button" onClick={open} className="min-w-0 cursor-pointer text-left text-callout font-semibold text-ink hover:underline">
              {opp.title}
            </button>
            <Markers opp={opp} members={false} />
          </div>
          <p className="mt-0.5 truncate text-footnote text-ink-tertiary">{meta.join(", ")}</p>
          <Countdown variant="text" {...countdownFor(opp)} className="mt-1 sm:hidden" />
        </div>
        <Countdown variant="text" {...countdownFor(opp)} className="hidden w-24 justify-end sm:flex" />
        <TrackButton opp={opp} applicationId={applicationId} className="shrink-0 sm:w-[104px]" />
        <ActionMenuButton actions={actions} label={`More for ${opp.title}`} className="shrink-0" />
      </li>
    </ActionContextMenu>
  )
}

function OpportunityDetail({
  opp,
  applicationId,
  onClose,
  onTodo,
  onShare,
}: {
  opp: Opportunity | null
  applicationId: string | undefined
  onClose: () => void
  onTodo: (opp: Opportunity) => void
  onShare: (opp: Opportunity) => void
}) {
  // Keep the last row while the dialog animates out.
  const [shown, setShown] = React.useState<Opportunity | null>(opp)
  if (opp && opp !== shown) setShown(opp)
  return (
    <Dialog open={!!opp} onOpenChange={(open) => !open && onClose()}>
      {shown ? (
        <DialogContent className="max-w-2xl" onClose={onClose}>
          <DialogHeader className="flex-row items-start gap-4">
            <Art opp={shown} shape="square" className="size-14 shrink-0 rounded-md" />
            <div className="min-w-0 space-y-1.5">
              <DialogTitle>{shown.title}</DialogTitle>
              {shown.organization ? <DialogDescription>{shown.organization}</DialogDescription> : null}
            </div>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <OpportunityMeta opp={shown} />
            {shown.summary ? <p className="max-w-reading text-body text-ink">{shown.summary}</p> : null}
            <dl className="grid gap-3 text-callout sm:grid-cols-[140px_1fr]">
              {shown.benefits ? <Fact label="What you get">{shown.benefits}</Fact> : null}
              {shown.eligibility ? <Fact label="Who can apply">{shown.eligibility}</Fact> : null}
              <Fact label="Deadline">
                {shown.rolling ? "Rolling" : shown.deadline || "Not listed"}
              </Fact>
              {shown.countries.length ? <Fact label="Countries">{shown.countries.join(", ")}</Fact> : null}
              {shown.tags.length ? <Fact label="Tags">{shown.tags.join(", ")}</Fact> : null}
            </dl>
            {shown.requirements.length ? (
              <div>
                <h3 className="mb-1.5 text-headline text-ink">What to prepare</h3>
                <ul className="list-disc space-y-1 pl-5 text-callout text-ink-secondary">
                  {shown.requirements.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <p className="text-footnote text-ink-tertiary">
              {FOUND_BY[shown.found_by] ?? FOUND_BY.community}
              {shown.verified_at ? `, checked ${formatAgo(shown.verified_at)}` : ""}
              {shown.source_url ? (
                <>
                  {" from "}
                  <a href={shown.source_url} target="_blank" rel="noopener noreferrer" className="underline">
                    the official page
                  </a>
                </>
              ) : null}
              . Confirm the details on the official page before you apply.
            </p>
          </DialogBody>
          <DialogFooter className="flex-row flex-wrap items-center justify-end">
            <ActionMenuButton
              actions={secondaryActions(shown, { onTodo, onShare }, false)}
              label="More actions"
              className="mr-auto"
            />
            {shown.link || shown.source_url ? (
              <a
                href={shown.link || shown.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ size: "sm", variant: "secondary" })}
              >
                Official page <ArrowUpRight />
              </a>
            ) : null}
            <TrackButton opp={shown} applicationId={applicationId} />
          </DialogFooter>
        </DialogContent>
      ) : null}
    </Dialog>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="font-medium text-ink-secondary">{label}</dt>
      <dd className="text-ink">{children}</dd>
    </>
  )
}

function TodoDialog({ opp, onClose }: { opp: Opportunity | null; onClose: () => void }) {
  const { create } = useTodoMutations()
  const [title, setTitle] = React.useState("")
  const [due, setDue] = React.useState("")
  // Prefill when a new opportunity opens the dialog.
  const [prefilled, setPrefilled] = React.useState<Opportunity | null>(null)
  if (opp && opp !== prefilled) {
    setPrefilled(opp)
    setTitle(`Apply: ${opp.title}`)
    setDue(opp.deadline_date ?? "")
  }
  return (
    <Dialog open={!!opp} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md" onClose={onClose}>
        <form
          className="flex min-h-0 flex-auto flex-col"
          onSubmit={(e) => {
            e.preventDefault()
            if (!opp || !title.trim()) return
            create.mutate(
              { title: title.trim(), due_date: due || null, opportunity_id: opp.id },
              {
                onSuccess: () => {
                  toastSuccess("Added to your to-dos")
                  onClose()
                },
                onError: (err) => toastError(err, "Couldn't add the to-do"),
              },
            )
          }}
        >
          <DialogHeader>
            <DialogTitle>Add a to-do</DialogTitle>
            <DialogDescription>It shows on your to-do list and in your calendar feed.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <Field label="To-do">
              <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} required />
            </Field>
            <Field label="Due">
              <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="quiet" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={create.isPending || !title.trim()}>
              Add
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function SubmitDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [form, setForm] = React.useState({
    title: "",
    organization: "",
    category: "startup" as OpportunityCategory,
    kind: "grant" as OpportunityKind,
    link: "",
    deadline: "",
    rolling: false,
    summary: "",
  })
  const [busy, setBusy] = React.useState(false)
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }))
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" onClose={() => onOpenChange(false)}>
        <form
          className="flex min-h-0 flex-auto flex-col"
          onSubmit={async (e) => {
            e.preventDefault()
            setBusy(true)
            try {
              await api.submitOpportunity({ ...form, deadline: form.rolling ? "" : form.deadline })
              toastSuccess("Thanks for sharing. It goes live once it has been reviewed.")
              onOpenChange(false)
            } catch (err) {
              toastError(err, "That didn't send. Check the details and try again.")
            } finally {
              setBusy(false)
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>Share an opportunity</DialogTitle>
            <DialogDescription>Help others find it. Shared opportunities are reviewed before they go public.</DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <Field label="Name" className="sm:col-span-2">
              <Input value={form.title} onChange={(e) => set("title", e.target.value)} minLength={3} maxLength={300} required />
            </Field>
            <Field label="Organization">
              <Input value={form.organization} onChange={(e) => set("organization", e.target.value)} maxLength={200} />
            </Field>
            <Field label="Link">
              <Input type="url" value={form.link} onChange={(e) => set("link", e.target.value)} placeholder="https://" required />
            </Field>
            <Field label="For">
              <Select value={form.category} onChange={(e) => set("category", e.target.value as OpportunityCategory)}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABELS[c]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Kind">
              <Select value={form.kind} onChange={(e) => set("kind", e.target.value as OpportunityKind)}>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABELS[k]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Deadline">
              <Input type="date" value={form.deadline} disabled={form.rolling} onChange={(e) => set("deadline", e.target.value)} />
            </Field>
            <label className="flex items-center gap-2 self-end pb-2 text-callout">
              <Checkbox checked={form.rolling} onCheckedChange={(value) => set("rolling", value === true)} />
              Rolling / always open
            </label>
            <Field label="Summary" className="sm:col-span-2">
              <Textarea value={form.summary} onChange={(e) => set("summary", e.target.value)} maxLength={4000} rows={3} />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="quiet" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={busy}>
              Share
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

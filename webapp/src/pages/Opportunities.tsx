import { Checkbox } from "../components/ui/checkbox"
import * as React from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import {
  ArrowUpRight,
  Bookmark,
  BookmarkPlus,
  Check,
  CalendarPlus,
  Download,
  Link2,
  ListPlus,
  Lock,
  PanelRightOpen,
  MapPin,
  Plus,
  Search,
  Settings2,
  Share2,
  SlidersHorizontal,
  Sparkles,
  Target,
  X,
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
import { useApplicationMutations } from "../lib/applications"
import { deadlineParts, sectionize, useLastVisit } from "../lib/feed"
import { formatAgo } from "../lib/format"
import {
  ALERTS,
  ALERT_LABELS,
  filtersToParams,
  sameFilters,
  suggestName,
  useMatchProfile,
  useSavedSearchMutations,
  useSavedSearches,
} from "../lib/matching"
import { useDrawerParam, useUrlParam } from "../lib/urlParams"
import { toastError, toastSuccess } from "../lib/toast"
import type { AlertFrequency, Opportunity, OpportunityCategory, OpportunityKind, OpportunitySort, SavedSearch, SearchFilters } from "../lib/types"
import {
  Button,
  Countdown,
  Field,
  Input,
  OpportunityArt,
  Select,
  Textarea,
  buttonVariants,
  chipVariants,
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
import { Skeleton, SkeletonStack } from "../components/ui/feedback"
import { Segmented } from "../components/layout/PageHeader"
import { useShellHeader } from "../components/layout/shellHeader"
import { ShareDialog } from "../components/share/ShareDialog"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../components/ui/menu"
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu"
import { ConfirmDialog } from "../components/kit/parts"
import { ScanDialog } from "./Scans"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "../components/ui/shadcn/sheet"
import discoverArt from "../assets/illustrations/discover.webp"
import { useIsMobile } from "../hooks/use-mobile"

const SORTS: { value: OpportunitySort; label: string }[] = [
  { value: "for_you", label: "For you" },
  { value: "relevance", label: "Best match" },
  { value: "deadline", label: "Closing soonest" },
  { value: "new", label: "Newest" },
]

const isSort = (value: string): value is OpportunitySort => SORTS.some((s) => s.value === value)

const COLUMN = "mx-auto w-full max-w-[47.5rem]"
const FLOATING_MENU_BUTTON = "size-8 rounded-full bg-surface-sunk text-ink-secondary hover:bg-separator hover:text-ink"

export function Opportunities() {
  const [query, setQuery] = useUrlParam("q")
  const [draft, setDraft] = React.useState(query)
  const [categoryParam, setCategory] = useUrlParam("category")
  const [kindParam, setKind] = useUrlParam("kind")
  const [sortParam, setSort] = useUrlParam("sort")
  const [country] = useUrlParam("country")
  const [soonParam, setSoon] = useUrlParam("soon")
  const [closedParam, setClosed] = useUrlParam("closed")
  const [newParam, setNew] = useUrlParam("new")
  const [hideParam, setHide] = useUrlParam("hide")
  const drawer = useDrawerParam()
  const category = isCategory(categoryParam) ? categoryParam : undefined
  const kind = isKind(kindParam) ? kindParam : undefined
  const hideTracked = hideParam === "tracked"
  // Searching ranks by best match until a sort is picked; best match needs words.
  const sort: OpportunitySort = isSort(sortParam) && (sortParam !== "relevance" || query) ? sortParam : query ? "relevance" : "deadline"
  const lastVisit = useLastVisit()

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
    country: country || undefined,
    sort,
    closing_within: soonParam ? 14 : undefined,
    new: newParam ? true : undefined,
    include_closed: closedParam ? true : undefined,
  })
  const facets = useOpportunityFacets()
  const tracked = useTrackedOpportunities()
  const items = list.data?.pages.flatMap((p) => p.items) ?? []
  const shown = hideTracked ? items.filter((o) => !tracked.data?.[o.id]) : items
  const sections = sectionize(shown, sort, lastVisit)
  const counts = new Map(facets.data?.categories.map((c) => [c.key, c.count]))

  const [todoFor, setTodoFor] = React.useState<Opportunity | null>(null)
  const [scanOpen, setScanOpen] = React.useState(false)
  const [submitOpen, setSubmitOpen] = React.useState(false)
  const [shareFor, setShareFor] = React.useState<Opportunity | null>(null)
  const handlers: OpportunityHandlers = {
    onOpen: (opp) => drawer.open(opp.id),
    onTodo: setTodoFor,
    onShare: setShareFor,
  }
  const filtered = !!(query || category || kind || country || soonParam || newParam || closedParam || hideTracked)
  const filters: SearchFilters = {
    q: query || undefined,
    category: category ?? null,
    kind: kind ?? null,
    country: country || null,
    closing_within: soonParam ? 14 : null,
  }
  const searchable = !!(query || category || kind || country || soonParam)
  const [saveOpen, setSaveOpen] = React.useState(false)
  const profile = useMatchProfile()
  const saved = useSavedSearches()
  const current = saved.data?.find((s) => sameFilters(s.filters, filters))
  useSavedSearchLink(saved.data)

  const header = React.useMemo(
    () => ({
      title: "Opportunities",
      actions: (
        <>
          <Button size="sm" variant="quiet" icon={<Plus />} data-tooltip="Share an opportunity you know about" onClick={() => setSubmitOpen(true)}>
            <span className="max-sm:sr-only">Share one</span>
          </Button>
          <Button size="sm" variant="primary" icon={<Sparkles />} onClick={() => setScanOpen(true)}>
            Find more
          </Button>
        </>
      ),
    }),
    [setSubmitOpen, setScanOpen],
  )
  useShellHeader(header)

  const [, setParams] = useSearchParams()
  const active: { key: string; label: string }[] = [
    ...(kind ? [{ key: "kind", label: KIND_LABELS[kind] }] : []),
    ...(country ? [{ key: "country", label: country }] : []),
    ...(newParam ? [{ key: "new", label: "New this week" }] : []),
    ...(soonParam ? [{ key: "soon", label: "Closing in 2 weeks" }] : []),
    ...(closedParam ? [{ key: "closed", label: "Including closed" }] : []),
    ...(hideTracked ? [{ key: "hide", label: "Tracked hidden" }] : []),
  ]
  const clearFilters = (keys: string[]) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        keys.forEach((k) => next.delete(k))
        return next
      },
      { replace: true },
    )

  // Section headings stick just under the control bar, whose height changes as it wraps.
  const barRef = React.useRef<HTMLDivElement>(null)
  const [barHeight, setBarHeight] = React.useState(0)
  React.useLayoutEffect(() => {
    const el = barRef.current
    if (!el) return
    const observer = new ResizeObserver(() => setBarHeight(el.offsetHeight))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const sortOptions = SORTS.filter((s) => s.value !== "relevance" || query).map((s) => (
    <option key={s.value} value={s.value}>
      {s.label}
    </option>
  ))
  const offsets = sections.map((_, i) => sections.slice(0, i).reduce((n, s) => n + s.items.length, 0))
  return (
    <div className={cn(COLUMN, "pb-16")}>
      <div ref={barRef} className="sticky top-0 z-20 -mx-3 -mt-2 space-y-2 bg-canvas px-3 pt-2 pb-3 sm:-mx-6 sm:px-6 after:pointer-events-none after:absolute after:inset-x-0 after:top-full after:bg-linear-to-b after:from-canvas after:to-transparent after:content-[''] after:h-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1 basis-32">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-tertiary" />
            <Input
              type="search"
              aria-label="Search opportunities"
              placeholder="Search name, funder, sector"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="h-control-sm w-full pr-10 pl-9 text-callout"
            />
            <SavedSearchesMenu
              searches={saved.data ?? []}
              current={current}
              canSave={searchable && !current}
              onSave={() => setSaveOpen(true)}
            />
          </div>
          <div className="min-w-0 max-sm:order-last max-sm:basis-full">
            <Segmented
              label="Audience"
              className="[scrollbar-width:none]"
              value={category ?? ""}
              onChange={(v) => setCategory(v)}
              options={[
                { value: "", label: "All", count: facets.data?.total },
                ...CATEGORIES.map((c) => ({ value: c as string, label: CATEGORY_LABELS[c], count: counts.get(c) ?? 0 })),
              ]}
            />
          </div>
          <FiltersPopover
            count={active.length}
            sort={
              <Select aria-label="Sort" className="h-control-sm text-footnote" value={sort} onChange={(e) => setSort(e.target.value)}>
                {sortOptions}
              </Select>
            }
            kind={kind}
            onKind={setKind}
            toggles={[
              { label: "New this week", on: !!newParam, set: (on) => setNew(on ? "1" : "") },
              { label: "Closing in 2 weeks", on: !!soonParam, set: (on) => setSoon(on ? "1" : "") },
              { label: "Include closed", on: !!closedParam, set: (on) => setClosed(on ? "1" : "") },
              { label: "Hide tracked", on: hideTracked, set: (on) => setHide(on ? "tracked" : "") },
            ]}
          />
          <Select
            aria-label="Sort"
            className="h-control-sm w-40 min-w-0 shrink-0 text-footnote max-sm:hidden"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            {sortOptions}
          </Select>
        </div>
        {active.length ? (
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Active filters">
            {active.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => clearFilters([f.key])}
                aria-label={`Remove filter: ${f.label}`}
                className={cn(
                  chipVariants({ tone: "forest" }),
                  "h-7 cursor-pointer pr-1.5 transition-colors hover:bg-highlight focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
                )}
              >
                {f.label}
                <X aria-hidden="true" />
              </button>
            ))}
            {active.length > 1 ? (
              <button
                type="button"
                onClick={() => clearFilters(active.map((f) => f.key))}
                className="cursor-pointer px-1.5 text-footnote text-link hover:underline"
              >
                Clear all
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {sort === "for_you" && profile.data && !profile.data.saved ? (
        <div className="mb-4 flex flex-col gap-3 rounded-lg bg-forest-soft px-4 py-3 sm:flex-row sm:items-center">
          <Target aria-hidden="true" className="hidden size-5 shrink-0 text-link sm:block" />
          <p className="min-w-0 flex-1 text-footnote text-ink">
            Tell us what you're looking for and this list puts the best fits first. You can also get alerts when new ones are added.
          </p>
          <Link to="/settings/matching" className={cn(buttonVariants({ size: "sm", variant: "brand" }))}>
            Set it up
          </Link>
        </div>
      ) : null}

      {list.isLoading ? (
        <ul className="space-y-3 pt-2" aria-busy="true">
          {Array.from({ length: 5 }, (_, i) => (
            <li key={i} className="flex gap-4 rounded-lg bg-surface p-4 shadow-elevation-1 sm:p-5">
              <Skeleton className="size-12 shrink-0 rounded-md max-sm:hidden" />
              <div className="min-w-0 flex-1 space-y-2.5">
                <Skeleton className="h-5 w-2/3" />
                <Skeleton className="h-3.5 w-1/3" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-3.5 w-1/2" />
              </div>
            </li>
          ))}
        </ul>
      ) : list.isError ? (
        <ErrorState title="Opportunities didn't load" description="Check your connection and try again." onRetry={() => void list.refetch()} />
      ) : shown.length === 0 && !list.hasNextPage ? (
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
          {sections.map((section, si) => (
            <section key={section.key} aria-label={section.title || "Opportunities"}>
              {section.title ? (
                <h2 style={{ top: barHeight }} className="sticky z-10 -mx-3 bg-canvas px-3 pt-3 pb-2 sm:-mx-6 sm:px-6 text-footnote font-semibold text-ink-secondary after:pointer-events-none after:absolute after:inset-x-0 after:top-full after:bg-linear-to-b after:from-canvas after:to-transparent after:content-[''] after:h-6">
                  {section.title}
                </h2>
              ) : null}
              <ul className="space-y-3 pb-4">
                {section.items.map((opp, i) => (
                  <FeedCard
                    key={opp.id}
                    index={offsets[si] + i}
                    opp={opp}
                    applicationId={tracked.data?.[opp.id]}
                    showAudience={!category}
                    {...handlers}
                  />
                ))}
              </ul>
            </section>
          ))}
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
        id={drawer.id}
        tracked={tracked.data}
        onClose={drawer.close}
        onTodo={setTodoFor}
        onShare={setShareFor}
      />
      <TodoDialog opp={todoFor} onClose={() => setTodoFor(null)} />
      <ScanDialog open={scanOpen} onOpenChange={setScanOpen} />
      <SubmitDialog open={submitOpen} onOpenChange={setSubmitOpen} />
      <ShareDialog opp={shareFor} onClose={() => setShareFor(null)} />
      <SaveSearchDialog open={saveOpen} filters={filters} onOpenChange={setSaveOpen} />
    </div>
  )
}

function SavedSearchesMenu({
  searches,
  current,
  canSave,
  onSave,
}: {
  searches: SavedSearch[]
  current: SavedSearch | undefined
  canSave: boolean
  onSave: () => void
}) {
  const navigate = useNavigate()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          variant="quiet"
          iconOnly
          aria-label="Saved searches"
          data-tooltip="Saved searches"
          icon={<Bookmark className={cn(current && "fill-current")} />}
          className={cn("absolute top-1/2 right-1 h-7 -translate-y-1/2 active:-translate-y-1/2", current ? "text-link" : "text-ink-secondary")}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" collisionPadding={8}>
        {searches.slice(0, 12).map((s) => (
          <DropdownMenuItem key={s.id} onSelect={() => navigate(`/opportunities?${filtersToParams(s.filters).toString()}`)}>
            <Check className={cn(s.id !== current?.id && "invisible")} />
            <span className="truncate">{s.name}</span>
          </DropdownMenuItem>
        ))}
        {searches.length ? <DropdownMenuSeparator /> : null}
        <DropdownMenuItem disabled={!canSave} onSelect={onSave}>
          <BookmarkPlus />
          {current ? "This search is saved" : "Save this search"}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/settings/matching")}>
          <Settings2 />
          Manage saved searches
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function FiltersPopover({
  count,
  sort,
  kind,
  onKind,
  toggles,
}: {
  count: number
  /** Phones have no room for Sort in the bar, so it moves in here. */
  sort: React.ReactElement<React.InputHTMLAttributes<HTMLElement>>
  kind: OpportunityKind | undefined
  onKind: (kind: string) => void
  toggles: { label: string; on: boolean; set: (on: boolean) => void }[]
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          size="sm"
          variant="secondary"
          icon={<SlidersHorizontal />}
          aria-label={count ? `Filters, ${count} on` : "Filters"}
          data-tooltip="Filters"
          className={cn("px-2.5", count && "border-forest/50 bg-forest-soft text-link hover:bg-forest-soft")}
        >
          {count ? <span className="tabular-nums">{count}</span> : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" collisionPadding={8} className="w-64 space-y-3 p-3">
        <Field label="Sort" className="sm:hidden">
          {sort}
        </Field>
        <Field label="Kind">
          <Select className="h-control-sm text-footnote" value={kind ?? ""} onChange={(e) => onKind(e.target.value)}>
            <option value="">All kinds</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </Select>
        </Field>
        <div className="space-y-0.5">
          {toggles.map((t) => (
            <label key={t.label} className="flex h-9 cursor-pointer items-center gap-2.5 rounded-sm px-1 text-callout text-ink hover:bg-highlight">
              <Checkbox checked={t.on} onCheckedChange={(value) => t.set(value === true)} />
              {t.label}
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

/** `?saved=<id>` (from an alert) opens that saved search's filters. */
function useSavedSearchLink(searches: { id: string; filters: SearchFilters }[] | undefined) {
  const [savedParam] = useUrlParam("saved")
  const navigate = useNavigate()
  React.useEffect(() => {
    if (!savedParam || !searches) return
    const found = searches.find((s) => s.id === savedParam)
    const params = found ? filtersToParams(found.filters) : new URLSearchParams()
    params.set("sort", "new")
    navigate({ pathname: "/opportunities", search: params.toString() }, { replace: true })
  }, [savedParam, searches, navigate])
}

function SaveSearchDialog({ open, filters, onOpenChange }: { open: boolean; filters: SearchFilters; onOpenChange: (open: boolean) => void }) {
  const { create } = useSavedSearchMutations()
  const [name, setName] = React.useState("")
  const [alerts, setAlerts] = React.useState<AlertFrequency>("daily")
  const [seenOpen, setSeenOpen] = React.useState(open)
  if (seenOpen !== open) {
    setSeenOpen(open)
    if (open) {
      setName(suggestName(filters))
      setAlerts("daily")
    }
  }
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    create.mutate(
      { name: name.trim(), filters, alerts },
      {
        onSuccess: () => {
          toastSuccess(alerts === "off" ? "Search saved." : "Search saved. We'll tell you when new listings match it.")
          onOpenChange(false)
        },
        onError: (err) => toastError(err, "That didn't save. Try again."),
      },
    )
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" onClose={() => onOpenChange(false)}>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Save this search</DialogTitle>
            <DialogDescription>Come back to these filters in one tap, and hear about new listings that match.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required autoFocus />
            </Field>
            <Field label="Alerts for new listings">
              <Select value={alerts} onChange={(e) => setAlerts(e.target.value as AlertFrequency)}>
                {ALERTS.map((a) => (
                  <option key={a} value={a}>
                    {ALERT_LABELS[a]}
                  </option>
                ))}
              </Select>
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="quiet" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={create.isPending || !name.trim()}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** On the For you list: which of the member's fields the listing mentions. */
function MatchLine({ opp }: { opp: Opportunity }) {
  if (!opp.match_terms?.length) return null
  return (
    <span className="inline-flex min-w-0 items-center gap-1 text-caption text-link">
      <Target aria-hidden="true" className="size-3 shrink-0" />
      <span className="truncate">Fits {opp.match_terms.slice(0, 2).join(", ")}</span>
    </span>
  )
}

function Markers({ opp, members = true, isNew = true }: { opp: Opportunity; members?: boolean; isNew?: boolean }) {
  return (
    <>
      {isNew && opp.is_new ? (
        <span className="inline-flex shrink-0 items-center gap-1 text-caption text-sun-ink">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-sun" />
          New
        </span>
      ) : null}
      <MatchLine opp={opp} />
      {members && opp.audience === "members" ? (
        <span className="inline-flex shrink-0 items-center gap-1 text-caption text-ink-tertiary">
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

export function TrackButton({ opp, applicationId, className }: { opp: Opportunity; applicationId: string | undefined; className?: string }) {
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

function copyLink(opp: Opportunity) {
  const url = `${window.location.origin}/opportunities/${encodeURIComponent(opp.slug || opp.id)}`
  navigator.clipboard.writeText(url).then(
    () => toastSuccess("Link copied"),
    () => toastError("That link didn't copy. Try again."),
  )
}

/** Everything but Track, which each surface shows as its own button. */
export function secondaryActions(opp: Opportunity, { onOpen, onTodo, onShare }: OpportunityHandlers, withOfficial = true): MenuAction[] {
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
  // Others can't open it until it's reviewed, so there's nothing to share yet.
  if (!opp.in_review)
    actions.push(
      { label: "Share", icon: <Share2 />, onSelect: () => onShare(opp) },
      { label: "Copy link", icon: <Link2 />, onSelect: () => copyLink(opp) },
    )
  if (official) actions.push({ kind: "separator" }, { label: "Official page", icon: <ArrowUpRight />, href: official })
  return actions
}

export function Art({ opp, shape, className }: { opp: Opportunity; shape: "banner" | "square"; className?: string }) {
  return <OpportunityArt seed={opp.slug || opp.id} category={opp.category} kind={opp.kind} shape={shape} className={className} />
}

interface FeedCardProps extends OpportunityHandlers {
  opp: Opportunity
  applicationId: string | undefined
  index: number
  /** False when an audience tab already says who it's for. */
  showAudience: boolean
}

function FeedCard({ opp, applicationId, index, showAudience, onOpen, onTodo, onShare }: FeedCardProps) {
  const actions = secondaryActions(opp, { onTodo, onShare })
  const due = deadlineParts(opp)
  const meta = [
    KIND_LABELS[opp.kind] ?? opp.kind,
    showAudience ? CATEGORY_LABELS[opp.category] : null,
    opp.audience === "members" ? "members only" : null,
    due.date,
  ].filter(Boolean).join(", ")
  const blurb = opp.summary || opp.eligibility
  const facts = !!(opp.benefits || opp.location)
  return (
    <ActionContextMenu actions={actions}>
      <li style={{ "--i": index } as React.CSSProperties} className="bl-enter">
        <article className="relative flex min-h-36 gap-4 rounded-lg bg-surface p-4 shadow-elevation-1 transition-[box-shadow,translate] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-elevation-2 motion-reduce:hover:translate-y-0 sm:p-5">
          <Art opp={opp} shape="square" className="size-12 shrink-0 rounded-md max-sm:hidden" />
          <div className="flex min-w-0 flex-1 flex-col">
            <h3 className="line-clamp-2 pr-16 sm:pr-32 text-title-3 text-balance text-ink">
              {/* The stretched hit area opens the details; the corner buttons sit above it. */}
              <button
                type="button"
                onClick={() => onOpen?.(opp)}
                className="cursor-pointer text-left after:absolute after:inset-0 after:rounded-lg after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-focus"
              >
                {opp.title}
              </button>
            </h3>
            {opp.organization ? <p className="truncate pr-16 sm:pr-32 text-footnote text-ink-tertiary">{opp.organization}</p> : null}
            {blurb ? <p className="mt-2 truncate text-callout font-normal text-ink-secondary">{blurb}</p> : null}
            {facts ? (
              <div className="mt-2 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 overflow-hidden text-footnote sm:flex-nowrap">
                {opp.benefits ? <span className="min-w-0 truncate font-semibold text-ink max-sm:basis-full">{opp.benefits}</span> : null}
                {opp.location ? (
                  <span className="inline-flex max-w-[45%] shrink-0 items-center gap-1 text-ink-secondary">
                    <MapPin aria-hidden="true" className="size-3.5 shrink-0 text-ink-tertiary" />
                    <span className="truncate">{opp.location}</span>
                  </span>
                ) : null}
              </div>
            ) : null}
            <div className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-2 text-footnote text-ink-secondary">
              <span className="first-letter:uppercase">{meta}</span>
              {due.daysLeft === null ? null : due.urgent ? (
                <Countdown {...countdownFor(opp)} />
              ) : (
                <span className="font-medium text-sun-ink tabular-nums">{due.daysLeft} days left</span>
              )}
            </div>
          </div>
          <div className="absolute top-3 right-3 z-20 flex items-center gap-1 sm:top-4 sm:right-4">
            <TrackToggle opp={opp} applicationId={applicationId} />
            <ActionMenuButton actions={actions} label={`More for ${opp.title}`} className={FLOATING_MENU_BUTTON} />
          </div>
        </article>
      </li>
    </ActionContextMenu>
  )
}

/** Bookmark toggle; untracking asks first when the application has progress to lose. */
function TrackToggle({ opp, applicationId }: { opp: Opportunity; applicationId: string | undefined }) {
  const track = useTrackOpportunity()
  const { remove } = useApplicationMutations()
  const client = useQueryClient()
  const [confirm, setConfirm] = React.useState(false)
  const [checking, setChecking] = React.useState(false)
  const busy = track.isPending || remove.isPending || checking

  const untrack = async (id: string) => {
    try {
      await remove.mutateAsync(id)
      toastSuccess("No longer tracking")
    } catch (err) {
      toastError(err, "That didn't update. Try again.")
    }
  }

  const toggle = async () => {
    if (!applicationId) {
      track.mutate(opp.id, {
        onSuccess: () => toastSuccess("Tracked. Deadline reminders are on."),
        onError: (err) => toastError(err, "That didn't track. Try again."),
      })
      return
    }
    setChecking(true)
    try {
      const app = await client.fetchQuery({
        queryKey: ["application", applicationId],
        queryFn: () => api.getApplication(applicationId),
        staleTime: 30_000,
      })
      const untouched = app.status === "saved" && !app.notes.trim() && !app.requirements.some((r) => r.done)
      if (untouched) await untrack(applicationId)
      else setConfirm(true)
    } catch (err) {
      toastError(err, "That didn't update. Try again.")
    } finally {
      setChecking(false)
    }
  }

  const on = !!applicationId
  return (
    <>
      <Button
        size="sm"
        variant="quiet"
        aria-label={`Track ${opp.title}`}
        aria-pressed={on}
        data-tooltip={on ? "Tracking. Select to stop" : undefined}
        disabled={busy}
        onClick={() => void toggle()}
        icon={<Bookmark className={cn(on && "fill-current")} />}
        className={cn(
          "h-8 rounded-full bg-surface-sunk text-ink-secondary hover:bg-separator hover:text-ink max-sm:w-8 max-sm:px-0",
          on && "bg-forest-soft text-link hover:bg-forest-soft hover:text-link",
        )}
      >
        <span className="max-sm:sr-only">Track</span>
      </Button>
      {applicationId ? (
        <ConfirmDialog
          open={confirm}
          onOpenChange={setConfirm}
          title="Stop tracking this?"
          description="Its application, with your status, notes and checklist, will be removed."
          confirm="Stop tracking"
          onConfirm={() => untrack(applicationId)}
        />
      ) : null}
    </>
  )
}

export function OpportunityDetail({
  id,
  tracked,
  onClose,
  onTodo,
  onShare,
}: {
  id: string | null
  tracked: Record<string, string> | undefined
  onClose: () => void
  onTodo: (opp: Opportunity) => void
  onShare: (opp: Opportunity) => void
}) {
  const detail = useOpportunity(id ?? undefined)
  // Keep the last row while the sheet animates out.
  const [shown, setShown] = React.useState<Opportunity | null>(null)
  const current = id ? detail.data : undefined
  if (current && current !== shown) setShown(current)
  const opp = current ?? (id ? null : shown)
  const failed = !!id && detail.isError
  const phone = useIsMobile()
  return (
    <Sheet open={!!id} onOpenChange={(open) => !open && onClose()}>
      {id || shown ? (
        <SheetContent
          side={phone ? "bottom" : "right"}
          className="gap-0 max-sm:h-[92dvh] sm:w-full sm:max-w-xl"
        >
          {opp ? (
            <>
              <ActionMenuButton
                actions={secondaryActions(opp, { onTodo, onShare }, false)}
                label="More actions"
                className={cn("absolute top-4 right-14 z-20", FLOATING_MENU_BUTTON)}
              />
              <SheetHeader className="flex-row items-start gap-4 border-b border-separator p-5 pr-24">
                <Art opp={opp} shape="square" className="size-14 shrink-0 rounded-md" />
                <div className="min-w-0 space-y-1.5">
                  <SheetTitle>{opp.title}</SheetTitle>
                  {opp.organization ? <SheetDescription>{opp.organization}</SheetDescription> : null}
                </div>
              </SheetHeader>
              <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
                <OpportunityMeta opp={opp} />
                {opp.summary ? <p className="max-w-reading text-body text-ink">{opp.summary}</p> : null}
                <dl className="grid gap-3 text-callout sm:grid-cols-[140px_1fr]">
                  {opp.benefits ? <Fact label="What you get">{opp.benefits}</Fact> : null}
                  {opp.eligibility ? <Fact label="Who can apply">{opp.eligibility}</Fact> : null}
                  <Fact label="Deadline">
                    {opp.rolling ? "Rolling" : opp.deadline || "Not listed"}
                  </Fact>
                  {opp.countries.length ? <Fact label="Countries">{opp.countries.join(", ")}</Fact> : null}
                  {opp.tags.length ? <Fact label="Tags">{opp.tags.join(", ")}</Fact> : null}
                </dl>
                {opp.requirements.length ? (
                  <div>
                    <h3 className="mb-1.5 text-headline text-ink">What to prepare</h3>
                    <ul className="list-disc space-y-1 pl-5 text-callout text-ink-secondary">
                      {opp.requirements.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <p className="text-footnote text-ink-tertiary">
                  {FOUND_BY[opp.found_by] ?? FOUND_BY.community}
                  {opp.verified_at ? `, checked ${formatAgo(opp.verified_at)}` : ""}
                  {opp.source_url ? (
                    <>
                      {" from "}
                      <a href={opp.source_url} target="_blank" rel="noopener noreferrer" className="underline">
                        the official page
                      </a>
                    </>
                  ) : null}
                  . Confirm the details on the official page before you apply.
                </p>
              </div>
              <SheetFooter className="mt-0 flex-row flex-wrap items-center justify-end border-t border-separator p-4 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))]">
                {opp.link || opp.source_url ? (
                  <a
                    href={opp.link || opp.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={buttonVariants({ size: "sm", variant: "secondary" })}
                  >
                    Official page <ArrowUpRight />
                  </a>
                ) : null}
                <Link
                  to={`/opportunities/${encodeURIComponent(opp.slug || opp.id)}`}
                  className={buttonVariants({ size: "sm", variant: "quiet" })}
                >
                  Open full page
                </Link>
                <TrackButton opp={opp} applicationId={tracked?.[opp.id]} />
              </SheetFooter>
            </>
          ) : (
            <>
              <SheetHeader className="flex-row items-start gap-4 border-b border-separator p-5 pr-24">
                {failed ? null : <Skeleton className="size-14 shrink-0 rounded-md" />}
                <div className="min-w-0 flex-1 space-y-2">
                  <SheetTitle className="sr-only">Opportunity</SheetTitle>
                  <SheetDescription className="sr-only">
                    {failed ? "Couldn't load opportunity details" : "Loading opportunity details"}
                  </SheetDescription>
                  {failed ? null : (
                    <>
                      <Skeleton className="h-6 w-3/4" />
                      <Skeleton className="h-4 w-1/2" />
                    </>
                  )}
                </div>
              </SheetHeader>
              <div className="min-h-0 flex-1 overflow-y-auto p-5" aria-busy={failed ? undefined : true}>
                {failed ? (
                  <ErrorState
                    compact
                    title="That opportunity didn't load"
                    description="Check your connection and try again."
                    onRetry={() => void detail.refetch()}
                  />
                ) : (
                  <SkeletonStack
                    role="status"
                    aria-label="Loading opportunity details"
                    className="space-y-3"
                    blocks={["h-5 w-1/2", "h-4 w-full", "h-4 w-5/6", "h-4 w-2/3", "h-24 w-full"]}
                  />
                )}
              </div>
            </>
          )}
        </SheetContent>
      ) : null}
    </Sheet>
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

export function TodoDialog({ opp, onClose }: { opp: Opportunity | null; onClose: () => void }) {
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
      <DialogContent className="max-w-2xl" onClose={() => onOpenChange(false)}>
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
            <div className="flex items-center gap-2 md:gap-4">
              <img src={discoverArt} alt="" width={500} height={500} className="bl-pop h-10 w-auto sm:h-20" />
              <div>
                <DialogTitle className="text-title-2">Share an opportunity</DialogTitle>
                <DialogDescription>Help others find it. Shared opportunities are reviewed before they go public.</DialogDescription>
              </div>
            </div>
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

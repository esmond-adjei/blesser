import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import {
  ArrowUpRight,
  Check,
  CalendarPlus,
  Download,
  ListPlus,
  MapPin,
  Plus,
  Search,
  Sparkles,
} from "lucide-react"
import { useAuth } from "../lib/auth"
import * as api from "../lib/api"
import {
  CATEGORIES,
  CATEGORY_DESCRIPTIONS,
  CATEGORY_LABELS,
  KINDS,
  KIND_LABELS,
  countdownFor,
  deadlineLabel,
  googleCalendarUrl,
  isCategory,
  isKind,
  useOpportunities,
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
  Chip,
  Countdown,
  Field,
  Input,
  OpportunityCard as Card,
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
import { ScanDialog } from "./Scans"

const SORTS = [
  { value: "deadline", label: "Closing soonest" },
  { value: "new", label: "Newest" },
]

export function Opportunities() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [query, setQuery] = useUrlParam("q")
  const [draft, setDraft] = React.useState(query)
  const [categoryParam, setCategory] = useUrlParam("category")
  const [kindParam, setKind] = useUrlParam("kind")
  const [sortParam, setSort] = useUrlParam("sort", "deadline")
  const [soonParam, setSoon] = useUrlParam("soon")
  const [closedParam, setClosed] = useUrlParam("closed")
  const category = isCategory(categoryParam) ? categoryParam : undefined
  const kind = isKind(kindParam) ? kindParam : undefined
  const sort = sortParam === "new" ? "new" : "deadline"

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
    include_closed: closedParam ? true : undefined,
  })
  const facets = useOpportunityFacets()
  const tracked = useTrackedOpportunities(!!user)
  const items = list.data?.pages.flatMap((p) => p.items) ?? []
  const total = list.data?.pages[0]?.total ?? 0
  const counts = new Map(facets.data?.categories.map((c) => [c.key, c.count]))

  const [detail, setDetail] = React.useState<Opportunity | null>(null)
  const [todoFor, setTodoFor] = React.useState<Opportunity | null>(null)
  const [scanOpen, setScanOpen] = React.useState(false)
  const [shareOpen, setShareOpen] = React.useState(false)

  const requireUser = (): boolean => {
    if (user) return true
    navigate(`/login?next=${encodeURIComponent("/opportunities")}`)
    return false
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h1 className="type-title-2">Opportunities</h1>
          <p className="text-callout text-ink-secondary max-w-2xl">
            Grants, accelerators, fellowships, scholarships and more, open to people in Ghana. Found and checked
            by agents against each opportunity's own page.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {user ? (
            <>
              <Button size="sm" onClick={() => setShareOpen(true)} icon={<Plus />}>
                Share one
              </Button>
              <Button size="sm" variant="brand" onClick={() => setScanOpen(true)} icon={<Sparkles />}>
                Find more
              </Button>
            </>
          ) : null}
        </div>
      </header>

      <nav aria-label="Audience" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <CategoryTile
          active={!category}
          label="Everything"
          description={`${facets.data?.total ?? "…"} open now`}
          onClick={() => setCategory("")}
        />
        {CATEGORIES.map((c) => (
          <CategoryTile
            key={c}
            active={category === c}
            label={CATEGORY_LABELS[c]}
            description={`${counts.get(c) ?? 0} open · ${CATEGORY_DESCRIPTIONS[c]}`}
            onClick={() => setCategory(category === c ? "" : c)}
          />
        ))}
      </nav>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3.5 size-[18px] -translate-y-1/2 text-ink-tertiary" />
          <Input
            aria-label="Search opportunities"
            placeholder="Search by name, funder, sector…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="w-full pl-10"
          />
        </div>
        <Select
          aria-label="Kind"
          className="w-auto min-w-[170px]"
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
        <Select aria-label="Sort" className="w-auto min-w-[160px]" value={sort} onChange={(e) => setSort(e.target.value)}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
        <Chip selected={!!soonParam} onClick={() => setSoon(soonParam ? "" : "1")}>
          Closing in 2 weeks{facets.data ? ` (${facets.data.closing_soon})` : ""}
        </Chip>
        <Chip selected={!!closedParam} onClick={() => setClosed(closedParam ? "" : "1")}>
          Include closed
        </Chip>
      </div>

      {list.isLoading ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="h-56 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
          ))}
        </div>
      ) : list.isError ? (
        <ErrorState title="Opportunities didn't load" description="Check your connection and try again." onRetry={() => void list.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          title={query || category || kind || soonParam ? "Nothing matches these filters" : "No opportunities yet"}
          description={
            user
              ? "Send agents to look for new ones, or share one you know about."
              : "Check back soon: agents add new opportunities as they find them."
          }
          action={
            user ? (
              <Button variant="primary" onClick={() => setScanOpen(true)} icon={<Sparkles />}>
                Find more
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <p className="text-callout text-ink-secondary" aria-live="polite">
            {total} {total === 1 ? "opportunity" : "opportunities"}
          </p>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {items.map((opp) => (
              <OpportunityCard
                key={opp.id}
                opp={opp}
                applicationId={tracked.data?.[opp.id]}
                onOpen={() => setDetail(opp)}
                onTodo={() => requireUser() && setTodoFor(opp)}
                requireUser={requireUser}
              />
            ))}
          </div>
          {list.hasNextPage ? (
            <div className="flex justify-center">
              <Button onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage}>
                {list.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            </div>
          ) : null}
        </>
      )}

      <OpportunityDetail
        opp={detail}
        applicationId={detail ? tracked.data?.[detail.id] : undefined}
        onClose={() => setDetail(null)}
        onTodo={(opp) => requireUser() && setTodoFor(opp)}
        requireUser={requireUser}
      />
      <TodoDialog opp={todoFor} onClose={() => setTodoFor(null)} />
      {user ? <ScanDialog open={scanOpen} onOpenChange={setScanOpen} /> : null}
      {user ? <ShareDialog open={shareOpen} onOpenChange={setShareOpen} /> : null}
    </div>
  )
}

function CategoryTile({
  active,
  label,
  description,
  onClick,
}: {
  active: boolean
  label: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "cursor-pointer rounded-lg border p-4 text-left transition-colors duration-160",
        active ? "border-forest bg-forest-soft" : "border-separator bg-surface hover:bg-surface-sunk",
      )}
    >
      <span className="block text-headline text-ink">{label}</span>
      <span className="mt-1 line-clamp-2 block text-footnote text-ink-secondary">{description}</span>
    </button>
  )
}

function OpportunityMeta({ opp }: { opp: Opportunity }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Countdown {...countdownFor(opp)} />
      <Chip tone="forest">{KIND_LABELS[opp.kind] ?? opp.kind}</Chip>
      <Chip>{CATEGORY_LABELS[opp.category] ?? opp.category}</Chip>
      {opp.location ? (
        <Chip icon={<MapPin />}>{opp.location}</Chip>
      ) : null}
    </div>
  )
}

function useTrack(opp: Opportunity, applicationId: string | undefined, requireUser: () => boolean) {
  const track = useTrackOpportunity()
  const navigate = useNavigate()
  return {
    pending: track.isPending,
    onTrack: () => {
      if (applicationId) return navigate("/applications")
      if (!requireUser()) return
      track.mutate(opp.id, {
        onSuccess: () => toastSuccess("Tracked. Deadline reminders are on."),
        onError: (err) => toastError(err, "That didn't track. Try again."),
      })
    },
  }
}

function TrackButton({
  opp,
  applicationId,
  requireUser,
}: {
  opp: Opportunity
  applicationId: string | undefined
  requireUser: () => boolean
}) {
  const { pending, onTrack } = useTrack(opp, applicationId, requireUser)
  if (applicationId)
    return (
      <Link to="/applications" className={buttonVariants({ size: "sm", variant: "quiet" })}>
        <Check /> Tracking
      </Link>
    )
  return (
    <Button size="sm" variant="primary" disabled={pending} onClick={onTrack} icon={<Plus />}>
      Track
    </Button>
  )
}

function CalendarButtons({ opp, compact }: { opp: Opportunity; compact?: boolean }) {
  const google = googleCalendarUrl(opp)
  if (!google) return null
  return (
    <>
      <a
        href={google}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={compact ? "Add to Google Calendar" : undefined}
        className={buttonVariants({ size: "sm", variant: compact ? "quiet" : "secondary", iconOnly: compact })}
        data-tooltip="Add the deadline to Google Calendar"
      >
        <CalendarPlus />
        {compact ? null : "Add to calendar"}
      </a>
      <a
        href={api.opportunityIcsUrl(opp.id)}
        className={buttonVariants({ size: "sm", iconOnly: true, variant: "quiet" })}
        aria-label="Download the deadline as an .ics file"
        data-tooltip="Download .ics (Apple Calendar, Outlook)"
      >
        <Download />
      </a>
    </>
  )
}

function OpportunityCard({
  opp,
  applicationId,
  onOpen,
  onTodo,
  requireUser,
}: {
  opp: Opportunity
  applicationId: string | undefined
  onOpen: () => void
  onTodo: () => void
  requireUser: () => boolean
}) {
  const { pending, onTrack } = useTrack(opp, applicationId, requireUser)
  return (
    <Card
      organization={opp.organization}
      title={
        <button type="button" onClick={onOpen} className="cursor-pointer text-left hover:underline">
          {opp.title}
        </button>
      }
      kind={KIND_LABELS[opp.kind] ?? opp.kind}
      amount={opp.benefits || undefined}
      audiences={[CATEGORY_LABELS[opp.category] ?? opp.category]}
      countdown={countdownFor(opp)}
      tracked={!!applicationId}
      onTrack={onTrack}
      trackDisabled={pending}
      actions={
        <>
          <CalendarButtons opp={opp} compact />
          <Button size="sm" variant="quiet" aria-label="Add a to-do" data-tooltip="Add a to-do" onClick={onTodo} icon={<ListPlus />} />
          {opp.link || opp.source_url ? (
            <a
              href={opp.link || opp.source_url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Open the official page for ${opp.title}`}
              data-tooltip="Official page"
              className={buttonVariants({ size: "sm", variant: "quiet", iconOnly: true })}
            >
              <ArrowUpRight />
            </a>
          ) : null}
        </>
      }
    >
      {opp.summary ? <p className="line-clamp-3 text-callout text-ink-secondary">{opp.summary}</p> : null}
    </Card>
  )
}

function OpportunityDetail({
  opp,
  applicationId,
  onClose,
  onTodo,
  requireUser,
}: {
  opp: Opportunity | null
  applicationId: string | undefined
  onClose: () => void
  onTodo: (opp: Opportunity) => void
  requireUser: () => boolean
}) {
  // Keep the last row while the dialog animates out.
  const [shown, setShown] = React.useState<Opportunity | null>(opp)
  if (opp && opp !== shown) setShown(opp)
  return (
    <Dialog open={!!opp} onOpenChange={(open) => !open && onClose()}>
      {shown ? (
        <DialogContent className="max-w-2xl" onClose={onClose}>
          <DialogHeader>
            <DialogTitle>{shown.title}</DialogTitle>
            {shown.organization ? <DialogDescription>{shown.organization}</DialogDescription> : null}
          </DialogHeader>
          <DialogBody className="space-y-4">
            <OpportunityMeta opp={shown} />
            {shown.summary ? <p className="max-w-reading text-body text-ink">{shown.summary}</p> : null}
            <dl className="grid gap-3 text-callout sm:grid-cols-[140px_1fr]">
              {shown.benefits ? <Fact label="What you get">{shown.benefits}</Fact> : null}
              {shown.eligibility ? <Fact label="Who can apply">{shown.eligibility}</Fact> : null}
              <Fact label="Deadline">
                {shown.rolling ? "Rolling" : shown.deadline || "Not listed"}
                {shown.deadline_date && !shown.rolling ? ` (${deadlineLabel(shown).toLowerCase()})` : ""}
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
              {shown.source === "agent" ? "Found by an agent" : "Shared by the community"}
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
          <DialogFooter className="flex-wrap">
            <Button size="sm" variant="quiet" onClick={() => onTodo(shown)} icon={<ListPlus />}>
              Add a to-do
            </Button>
            <CalendarButtons opp={shown} />
            <TrackButton opp={shown} applicationId={applicationId} requireUser={requireUser} />
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

function ShareDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
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
              const saved = await api.submitOpportunity({ ...form, deadline: form.rolling ? "" : form.deadline })
              toastSuccess(
                saved.status === "published"
                  ? "Published. Thanks for sharing."
                  : "Thanks for sharing. It goes public once it has been reviewed.",
              )
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
              <input type="checkbox" className="size-4 accent-forest" checked={form.rolling} onChange={(e) => set("rolling", e.target.checked)} />
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

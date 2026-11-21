import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowUpRight, ChevronRight, EyeOff, Lock, MapPin } from "lucide-react"
import { Chip, Countdown, buttonVariants, cn, formatDay } from "@blesser/ui"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { ShareDialog } from "../components/share/ShareDialog"
import { ActionMenuButton } from "../components/ui/menu"
import { ApiError } from "../lib/api"
import { formatAgo } from "../lib/format"
import { CATEGORY_LABELS, KIND_LABELS, countdownFor, useOpportunity, useTrackedOpportunities } from "../lib/opportunities"
import { Art, TodoDialog, TrackButton, secondaryActions } from "./Opportunities"

export function OpportunityPage() {
  const { id } = useParams()
  const opportunity = useOpportunity(id)
  const tracked = useTrackedOpportunities()
  const [dialog, setDialog] = useState<{ type: "todo" | "share"; id: string } | null>(null)
  const opp = opportunity.data

  if (opportunity.isPending) {
    return <p className="text-callout text-ink-secondary" role="status">Loading opportunity…</p>
  }
  if (!opp) {
    const back = <Link to="/opportunities" className={buttonVariants({ size: "sm", variant: "secondary" })}>Browse opportunities</Link>
    if (opportunity.error instanceof ApiError && opportunity.error.status === 404) {
      return <EmptyState title="Opportunity not found" description="This opportunity may have moved or been removed." action={back} />
    }
    return <ErrorState title="Couldn't load the opportunity" description="Try opening it again." action={back} onRetry={() => void opportunity.refetch()} />
  }

  const official = opp.link || opp.source_url
  const actions = secondaryActions(opp, {
    onTodo: () => setDialog({ type: "todo", id: opp.id }),
    onShare: () => setDialog({ type: "share", id: opp.id }),
  }, false)
  const sections = [
    { title: "About", text: opp.summary },
    { title: "What you get", text: opp.benefits },
    { title: "Who can apply", text: opp.eligibility },
  ]

  return (
    <div className="bl-enter mx-auto max-w-6xl space-y-6">
      <header className="grid min-w-0 items-center gap-5 rounded-xl bg-sun-soft p-4 sm:p-6 md:grid-cols-[minmax(0,1fr)_12rem] lg:p-8">
        <div className="min-w-0 space-y-3">
          <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-footnote text-sun-ink">
            <Link to="/opportunities" className="hover:underline">Opportunities</Link>
            <ChevronRight aria-hidden="true" className="size-3.5" />
            <span>{KIND_LABELS[opp.kind] ?? opp.kind}</span>
          </nav>
          <div className="space-y-1">
            {opp.organization ? <p className="text-callout text-ink-secondary wrap-break-word">{opp.organization}</p> : null}
            <h1 className="font-display text-3xl font-bold text-ink wrap-break-word">{opp.title}</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Chip>{CATEGORY_LABELS[opp.category]}</Chip>
            {opp.location ? <Chip icon={<MapPin aria-hidden="true" />} className="h-auto min-h-6 max-w-full whitespace-normal wrap-anywhere">{opp.location}</Chip> : null}
            {opp.in_review ? (
              <Chip icon={<EyeOff aria-hidden="true" />}>Only you can see this</Chip>
            ) : opp.audience === "members" ? <Chip icon={<Lock aria-hidden="true" />}>Members only</Chip> : null}
            {opp.is_new && !opp.in_review ? <Chip>New</Chip> : null}
          </div>
        </div>
        <Art opp={opp} shape="banner" className="rounded-lg" />
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem] lg:gap-10">
        <aside className="space-y-3 lg:sticky lg:top-10 lg:col-start-2 lg:row-start-1" aria-label="Deadline and actions">
          <div className="space-y-3 rounded-xl border border-separator bg-surface p-4 sm:p-5">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-headline text-ink">Deadline</h2>
              <ActionMenuButton actions={actions} label="More actions" />
            </div>
            <Countdown {...countdownFor(opp)} className="max-w-full whitespace-normal wrap-anywhere" />
            {opp.deadline_date && !opp.rolling ? (
              <p className="text-callout text-ink-secondary">
                <time dateTime={opp.deadline_date}>{formatDay(opp.deadline_date)}</time>
              </p>
            ) : null}
            <div className="grid gap-2">
              <TrackButton opp={opp} applicationId={tracked.data?.[opp.id]} className="w-full" />
              {official ? (
                <a href={official} target="_blank" rel="noopener noreferrer" className={cn(buttonVariants({ size: "sm", variant: "secondary" }), "w-full")}>
                  Official page <ArrowUpRight aria-hidden="true" />
                </a>
              ) : null}
            </div>
          </div>
          <p className="rounded-lg bg-forest-soft p-4 text-footnote text-link">
            {opp.verified_at ? `Checked ${formatAgo(opp.verified_at)} from the official page. ` : ""}
            Confirm the details before you apply.
          </p>
        </aside>

        <article className="min-w-0 max-w-reading space-y-6 lg:col-start-1 lg:row-start-1">
          {sections.map(({ title, text }) => text ? (
            <section key={title} className="space-y-2">
              <h2 className="text-headline text-ink">{title}</h2>
              <p className="whitespace-pre-line text-body text-ink-secondary wrap-anywhere">{text}</p>
            </section>
          ) : null)}
          {opp.requirements.length ? (
            <section className="space-y-2">
              <h2 className="text-headline text-ink">What you'll need</h2>
              <ul className="list-disc space-y-1 pl-5 text-body text-ink-secondary wrap-anywhere">
                {[...new Set(opp.requirements)].map((requirement) => <li key={requirement}>{requirement}</li>)}
              </ul>
            </section>
          ) : null}
        </article>
      </div>

      <TodoDialog opp={dialog?.type === "todo" && dialog.id === opp.id ? opp : null} onClose={() => setDialog(null)} />
      <ShareDialog opp={dialog?.type === "share" && dialog.id === opp.id ? opp : null} onClose={() => setDialog(null)} />
    </div>
  )
}

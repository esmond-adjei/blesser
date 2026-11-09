import { OpportunityCard, buttonVariants } from "@blesser/ui"
import type { PublicOpportunity } from "../lib/api"
import { categoryLabel, countdownFor, kindLabel } from "../lib/format"
import { PlusIcon } from "./icons"

export function SiteCard({ opp, trackUrl }: { opp: PublicOpportunity; trackUrl: string }) {
  return (
    <OpportunityCard
      // The card's own Track is an onClick button; the site needs a link that works without JS.
      className="relative h-full [&_button]:hidden"
      organization={opp.organization || undefined}
      title={
        <a
          href={`/opportunities/${encodeURIComponent(opp.slug)}`}
          className="text-ink no-underline after:absolute after:inset-0 after:rounded-lg after:content-[''] hover:underline"
        >
          {opp.title}
        </a>
      }
      kind={kindLabel(opp.kind)}
      amount={opp.benefits || undefined}
      audiences={[categoryLabel(opp.category)]}
      countdown={countdownFor(opp)}
      actions={
        opp.closed ? null : (
          <a
            href={trackUrl}
            aria-label={`Track ${opp.title}`}
            className={`relative z-10 ${buttonVariants({ variant: "primary", size: "sm" })}`}
          >
            <PlusIcon />
            Track
          </a>
        )
      }
    >
      {opp.summary ? <p className="m-0 line-clamp-3 text-callout text-ink-secondary">{opp.summary}</p> : null}
    </OpportunityCard>
  )
}

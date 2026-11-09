import { Chip, Countdown, buttonVariants, cn } from "@blesser/ui"
import type { PublicOpportunity } from "../lib/api"
import { categoryLabel, countdownFor, kindLabel } from "../lib/format"
import { ArrowRightIcon, PlusIcon } from "./icons"

const TILE: Record<string, string> = {
  startup: "bg-forest text-on-forest",
  research: "bg-forest-soft text-link",
  student: "bg-surface-sunk text-forest",
}

function initials(name: string): string {
  const words = name.split(/\s+/).filter((w) => /^[A-Z0-9]/.test(w))
  return (words.length ? words : name.split(/\s+/))
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
}

export function SiteCard({ opp, trackUrl }: { opp: PublicOpportunity; trackUrl: string }) {
  const href = `/opportunities/${encodeURIComponent(opp.slug)}`
  return (
    <article className="group relative flex h-full flex-col rounded-lg bg-surface p-4 shadow-elevation-1 transition-[box-shadow,transform] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-elevation-2 motion-reduce:hover:translate-y-0">
      <div className={cn("relative grid h-36 place-items-center overflow-hidden rounded-md pb-9", TILE[opp.category] ?? TILE.student)}>
        <span aria-hidden="true" className="absolute -top-6 -right-6 size-20 rounded-full bg-sun" />
        <span aria-hidden="true" className="relative font-display text-[44px] leading-none font-bold tracking-[-0.03em]">
          {initials(opp.organization || opp.title)}
        </span>
        <span className="absolute bottom-3 left-3 rounded-full bg-surface p-1 shadow-elevation-1">
          <Countdown {...countdownFor(opp)} />
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-2 px-1 pt-4">
        <div className="flex flex-wrap gap-2">
          <Chip tone="forest">{kindLabel(opp.kind)}</Chip>
          <Chip>{categoryLabel(opp.category)}</Chip>
        </div>
        <h3 className="m-0 text-title-3 text-balance text-ink">
          <a href={href} className="text-ink no-underline after:absolute after:inset-0 after:rounded-lg after:content-['']">
            {opp.title}
          </a>
        </h3>
        {opp.organization ? <p className="m-0 truncate text-callout text-ink-secondary">{opp.organization}</p> : null}
        {opp.benefits ? <p className="m-0 text-[15px] leading-[22px] font-semibold text-ink">{opp.benefits}</p> : null}
        {opp.summary ? <p className="m-0 line-clamp-3 text-callout text-ink-secondary">{opp.summary}</p> : null}
        <div className="mt-auto flex items-center justify-between gap-3 border-t border-separator pt-3">
          <span aria-hidden="true" className="inline-flex items-center gap-2 text-callout font-semibold text-ink group-hover:underline">
            View details
            <span className="grid size-6 place-items-center rounded-full bg-forest text-on-forest [&_svg]:size-3.5">
              <ArrowRightIcon />
            </span>
          </span>
          {opp.closed ? null : (
            <a href={trackUrl} aria-label={`Track ${opp.title}`} className={cn("relative z-10", buttonVariants({ variant: "primary", size: "sm" }))}>
              <PlusIcon />
              Track
            </a>
          )}
        </div>
      </div>
    </article>
  )
}

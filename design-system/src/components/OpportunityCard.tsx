import * as React from "react"
import { cn } from "../lib"
import { Button } from "./Button"
import { Chip } from "./Chip"
import { Countdown, type CountdownProps } from "./Countdown"

export interface OpportunityCardProps {
  organization?: string
  title: React.ReactNode
  kind: string
  amount?: string
  amountNote?: string
  audiences?: string[]
  countdown?: CountdownProps
  tracked?: boolean
  onTrack?: () => void
  trackDisabled?: boolean
  /** Extra content between the chips and the footer, such as a summary. */
  children?: React.ReactNode
  /** Extra footer actions, placed before the track button. */
  actions?: React.ReactNode
  /** A control pinned to the card's top-right corner, above the stretched link. */
  cornerAction?: React.ReactNode
  /** Full-bleed artwork above the content, such as OpportunityArt. */
  media?: React.ReactNode
  className?: string
}

const CHECK = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
)
const PLUS = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden="true">
    <path d="M5 12h14M12 5v14" />
  </svg>
)

function initials(name: string): string {
  const words = name.split(/\s+/).filter((w) => /^[A-Z0-9]/.test(w))
  return (words.length ? words : name.split(/\s+/)).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("")
}

export function OpportunityCard({
  organization,
  title,
  kind,
  amount,
  amountNote,
  audiences = [],
  countdown,
  tracked,
  onTrack,
  trackDisabled,
  children,
  actions,
  cornerAction,
  media,
  className,
}: OpportunityCardProps) {
  return (
    <article
      className={cn(
        "relative flex flex-col gap-3 overflow-hidden rounded-lg border border-separator bg-surface p-5 shadow-elevation-1 transition-[box-shadow,translate] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-elevation-2 motion-reduce:hover:translate-y-0",
        className,
      )}
    >
      {cornerAction ? <div className="absolute top-4 right-4 z-20">{cornerAction}</div> : null}
      {media ? <div className="-mx-5 -mt-5 mb-1">{media}</div> : null}
      {organization ? (
        <div className={cn("flex min-w-0 items-center gap-2 text-callout text-ink-secondary", cornerAction && "pr-10")}>
          <span
            aria-hidden="true"
            className="grid size-7 shrink-0 place-items-center rounded-full bg-forest-soft font-display text-xs leading-none font-bold text-link"
          >
            {initials(organization)}
          </span>
          <span className="truncate">{organization}</span>
        </div>
      ) : null}
      <h3 className={cn("m-0 text-title-3 text-balance text-ink", cornerAction && "pr-10")}>{title}</h3>
      {amount ? (
        <div className="line-clamp-2 text-[15px] leading-[22px] font-semibold text-ink">
          {amount}
          {amountNote ? <span className="ml-1.5 font-normal text-ink-tertiary">{amountNote}</span> : null}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Chip tone="forest">{kind}</Chip>
        {audiences.map((a) => (
          <Chip key={a}>{a}</Chip>
        ))}
      </div>
      {children}
      <div className="relative z-10 mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-separator pt-3">
        <Countdown {...(countdown ?? { rolling: true })} />
        <div className="flex flex-wrap items-center gap-1">
          {actions}
          {tracked ? (
            <Button size="sm" variant="quiet" icon={CHECK} onClick={onTrack} disabled={trackDisabled}>
              Tracking
            </Button>
          ) : (
            <Button size="sm" variant="primary" icon={PLUS} onClick={onTrack} disabled={trackDisabled}>
              Track
            </Button>
          )}
        </div>
      </div>
    </article>
  )
}

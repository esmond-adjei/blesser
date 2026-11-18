import * as React from "react"
import { Check } from "lucide-react"
import { Chip, Countdown, daysUntil } from "@blesser/ui"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../../../webapp/src/components/ui/menu"
import type { Review, TrackedApplication } from "../shared/types"
import { send } from "../shared/ui"

export function Opportunity({ tabId, pageTitle, review }: { tabId: number | null; pageTitle: string; review: Review | null }) {
  const [details, setDetails] = React.useState<TrackedApplication | null>(null)
  const [marking, setMarking] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const opportunityId = review?.matchedOpportunityId

  React.useEffect(() => {
    if (tabId === null || !opportunityId) return
    let live = true
    void send<TrackedApplication | null>({ type: "trackedApplication", tabId }).then((details) => {
      if (live) setDetails(details)
    }, () => {})
    return () => { live = false }
  }, [tabId, opportunityId])

  const title = details?.title || pageTitle || review?.title || review?.host || "Current page"
  const deadline = details?.deadline_date
  const actions: MenuAction[] = opportunityId && !review?.applied && tabId !== null ? [{
    label: "Mark as applied",
    icon: <Check />,
    disabled: marking,
    onSelect: async () => {
      setMarking(true)
      setError(null)
      try {
        await send<Review>({ type: "markApplied", tabId })
      } catch (err) {
        setError(err instanceof Error ? err.message : "Couldn't mark it as applied")
      } finally {
        setMarking(false)
      }
    },
  }] : []

  const card = (
    <section aria-label="Opportunity on this page" className="bl-enter space-y-2 rounded-lg border border-separator bg-surface p-3.5">
      <div className="flex items-start justify-between gap-2">
        <h1 className="min-w-0 wrap-anywhere type-title-3 text-ink">{title}</h1>
        {actions.length ? <ActionMenuButton actions={actions} label="Opportunity actions" className="-my-1" /> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {details ? (
          <Countdown
            daysLeft={deadline ? daysUntil(deadline) : null}
            date={deadline}
            rolling={!deadline && /\brolling\b/i.test(details.deadline)}
            label={details.deadline}
            className="max-w-full whitespace-normal"
          />
        ) : null}
        {opportunityId ? (
          <Chip tone="forest" icon={<Check aria-hidden="true" />}>{review.applied ? "Marked as applied" : "Tracked"}</Chip>
        ) : review ? (
          <Chip>No tracked match</Chip>
        ) : (
          <Chip>Tracking unknown</Chip>
        )}
      </div>
      {error && opportunityId ? <p role="alert" className="text-footnote text-critical">{error}</p> : null}
    </section>
  )
  return actions.length ? <ActionContextMenu actions={actions}>{card}</ActionContextMenu> : card
}

import * as React from "react"
import { Check } from "lucide-react"
import { Chip, Countdown, daysUntil } from "@blesser/ui"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../../../webapp/src/components/ui/menu"
import type { Review, TrackedApplication } from "../shared/types"
import { send } from "../shared/ui"

export function Opportunity({ tabId, pageTitle, review }: { tabId: number | null; pageTitle: string; review: Review | null }) {
  // undefined: not known yet (or Blesser can't read the page); null: checked, nothing tracked matches.
  const [lookup, setLookup] = React.useState<{ key: string; details: TrackedApplication | null } | null>(null)
  const [marking, setMarking] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const key = `${tabId}|${pageTitle}|${review?.at ?? ""}`
  // Keep the last answer for this page while a fresh check (after a fill) runs, so the chip doesn't flicker.
  const details = lookup?.key.startsWith(`${tabId}|${pageTitle}|`) ? lookup.details : undefined

  React.useEffect(() => {
    if (tabId === null) return
    let live = true
    void send<TrackedApplication | null>({ type: "trackedApplication", tabId }).then(
      (found) => live && setLookup({ key, details: found }),
      () => {},
    )
    return () => { live = false }
  }, [tabId, key])

  const title = details?.title || pageTitle || review?.title || review?.host || "Current page"
  const deadline = details?.deadline_date
  const applied = !!details?.applied || !!review?.applied
  const actions: MenuAction[] = details && !applied && tabId !== null ? [{
    label: "Mark as applied",
    icon: <Check />,
    disabled: marking,
    onSelect: async () => {
      setMarking(true)
      setError(null)
      try {
        const next = await send<TrackedApplication>({ type: "markApplied", tabId })
        setLookup({ key, details: next })
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
        {details ? (
          <Chip tone="forest" icon={<Check aria-hidden="true" />}>{applied ? "Marked as applied" : "Tracked"}</Chip>
        ) : details === null ? (
          <Chip>Not in your applications</Chip>
        ) : null}
      </div>
      {error && details ? <p role="alert" className="text-footnote text-critical">{error}</p> : null}
    </section>
  )
  return actions.length ? <ActionContextMenu actions={actions}>{card}</ActionContextMenu> : card
}

import * as React from "react"
import { BookmarkPlus, Check, ListChecks } from "lucide-react"
import { Button, Chip, Countdown, daysUntil } from "@blesser/ui"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../../../webapp/src/components/ui/menu"
import type { ApplicationStatus, NewApplication, PageDetails, Review, TrackedApplication } from "../shared/types"
import { send } from "../shared/ui"
import { SaveDialog } from "./SaveDialog"
import { STATUSES, confident, deadlineText, statusLabel } from "./statuses"

export function Opportunity({
  tabId,
  pageTitle,
  review,
  onNotice,
}: {
  tabId: number | null
  pageTitle: string
  review: Review | null
  onNotice: (text: string) => void
}) {
  // undefined: not known yet (or Blesser can't read the page); null: checked, nothing tracked matches.
  const [lookup, setLookup] = React.useState<{ key: string; details: TrackedApplication | null } | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [draft, setDraft] = React.useState<PageDetails | null>(null)
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

  const run = async (work: () => Promise<TrackedApplication | null | void>) => {
    if (tabId === null) return
    setBusy(true)
    setError(null)
    try {
      const next = await work()
      if (next) setLookup({ key, details: next })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.")
    } finally {
      setBusy(false)
    }
  }

  const save = async (application: NewApplication) => {
    const saved = await send<TrackedApplication>({ type: "saveApplication", tabId: tabId!, application })
    setLookup({ key, details: saved })
    setDraft(null)
    onNotice(`Saved to your applications as ${statusLabel(saved.status)}`)
  }

  // Saves straight away when the page names the opportunity and its deadline; otherwise asks for what's missing.
  const startSave = () =>
    run(async () => {
      const found = await send<PageDetails>({ type: "pageDetails", tabId: tabId! })
      if (!confident(found)) {
        setDraft(found)
        return
      }
      const date = found.deadline?.date ?? null
      await save({
        title: found.title,
        organization: found.organization,
        link: "",
        deadline: date ? deadlineText(date) : "Rolling",
        deadline_date: date,
        status: "preparing",
      })
    })

  const title = details?.title || pageTitle || review?.title || review?.host || "Current page"
  const deadline = details?.deadline_date
  const actions: MenuAction[] =
    details && tabId !== null
      ? [{
          kind: "radio",
          label: "Status",
          icon: <ListChecks />,
          value: details.status,
          options: STATUSES,
          onChange: (status) => void run(() => send<TrackedApplication>({ type: "setStatus", tabId, status: status as ApplicationStatus })),
        }]
      : []

  const card = (
    <section aria-label="Opportunity on this page" aria-busy={busy} className="bl-enter space-y-2 rounded-lg border border-separator bg-surface p-3.5">
      <div className="flex items-start justify-between gap-2">
        <h1 className="min-w-0 wrap-anywhere type-title-3 text-ink">{title}</h1>
        {actions.length ? <ActionMenuButton actions={actions} label="Opportunity actions" className="-my-1" /> : null}
      </div>
      {details ? (
        <div className="flex flex-wrap items-center gap-2">
          <Countdown
            daysLeft={deadline ? daysUntil(deadline) : null}
            date={deadline}
            rolling={!deadline && /\brolling\b/i.test(details.deadline)}
            label={details.deadline}
            className="max-w-full whitespace-normal"
          />
          <Chip tone="forest" icon={<Check aria-hidden="true" />}>{statusLabel(details.status)}</Chip>
        </div>
      ) : details === null ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Chip>Not in your applications</Chip>
          <Button size="sm" variant="secondary" icon={<BookmarkPlus aria-hidden="true" />} disabled={busy} onClick={() => void startSave()}>
            {busy ? "Saving…" : "Save to my applications"}
          </Button>
        </div>
      ) : null}
      {error ? <p role="alert" className="text-footnote text-critical">{error}</p> : null}
      {draft ? (
        <SaveDialog open details={draft} onClose={() => setDraft(null)} onSave={save} />
      ) : null}
    </section>
  )
  return actions.length ? <ActionContextMenu actions={actions}>{card}</ActionContextMenu> : card
}

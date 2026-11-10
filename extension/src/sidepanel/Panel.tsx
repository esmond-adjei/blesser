import * as React from "react"
import { ArrowUpRight, Check, Flag, Footprints, LogOut, Settings as SettingsIcon, Sparkles } from "lucide-react"
import { Button, Logo, Select, cn } from "@blesser/ui"
import { counts } from "../shared/review"
import type { Prefs, Review, Status } from "../shared/types"
import { send } from "../shared/ui"
import { ReportDialog } from "./ReportDialog"
import { ReviewList } from "./ReviewList"
import { usePanelTab } from "./usePanelTab"

function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (next: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors duration-160 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-forest" : "bg-control-border",
      )}
    >
      <span className={cn("absolute top-0.5 size-4 rounded-full bg-surface shadow-elevation-1 transition-all", checked ? "left-[18px]" : "left-0.5")} />
    </button>
  )
}

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })

function Summary({ review }: { review: Review }) {
  const c = counts(review)
  return (
    <p className="flex flex-wrap items-baseline gap-x-1.5 text-footnote text-ink-secondary" aria-live="polite">
      <span className="font-semibold text-ink tabular-nums">{c.filled}</span> filled
      <span aria-hidden="true">·</span>
      <span className="font-semibold text-ink tabular-nums">{c.drafted}</span> drafted
      <span aria-hidden="true">·</span>
      <span className="font-semibold text-ink tabular-nums">{c.needs}</span> {c.needs === 1 ? "needs" : "need"} you
      <span className="ml-auto text-[12px] text-ink-tertiary">{time(review.at)}</span>
    </p>
  )
}

function Moved({ moved }: { moved: NonNullable<Review["moved"]> }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-info-soft px-3 py-2" role="status">
      <Footprints className="mt-0.5 size-4 shrink-0 text-info" aria-hidden="true" />
      <p className="text-footnote text-ink">
        {moved === "navigated" ? "You're on a new page or step." : "New fields appeared on this page."} Fill this step when you're ready; the list below is from before.
      </p>
    </div>
  )
}

function Applied({ review, tabId }: { review: Review; tabId: number }) {
  const [marking, setMarking] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  if (!review.matchedOpportunityId) return null
  if (review.applied)
    return (
      <p className="flex items-center gap-1.5 text-callout text-positive">
        <Check className="size-4" aria-hidden="true" /> Marked as applied
      </p>
    )
  return (
    <div className="rounded-md border border-separator bg-surface px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-footnote text-ink-secondary">You track this one. Submitted it?</p>
        <Button
          size="sm"
          variant="secondary"
          disabled={marking}
          onClick={async () => {
            setMarking(true)
            setError(null)
            try {
              await send<Review>({ type: "markApplied", tabId })
            } catch (err) {
              setError(err instanceof Error ? err.message : "Couldn't mark it")
            } finally {
              setMarking(false)
            }
          }}
        >
          Mark as applied
        </Button>
      </div>
      {error ? <p role="alert" className="mt-1.5 text-footnote text-critical">{error}</p> : null}
    </div>
  )
}

export function Panel() {
  const [status, setStatus] = React.useState<Status | null>(null)
  const { tabId, review } = usePanelTab()
  const [busy, setBusy] = React.useState(false)
  const [failure, setFailure] = React.useState<{ tabId: number | null; text: string } | null>(null)
  const error = failure && (failure.tabId === null || failure.tabId === tabId) ? failure.text : null
  const setError = React.useCallback((text: string | null) => setFailure(text === null ? null : { tabId, text }), [tabId])
  const [reporting, setReporting] = React.useState(false)
  const [notice, setNotice] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    try {
      const next = await send<Status>({ type: "status" })
      if (next.me && next.prefs.fillAs !== "me" && !next.me.projects.some((p) => p.id === next.prefs.fillAs)) {
        next.prefs = { ...next.prefs, fillAs: "me" }
        void send({ type: "prefs", prefs: next.prefs })
      }
      setStatus(next)
    } catch (err) {
      setFailure({ tabId: null, text: err instanceof Error ? err.message : "Couldn't load" })
    }
  }, [])

  React.useEffect(() => {
    void load()
    const onFocus = () => void load()
    const onAuth = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === "local" && changes.auth) void load()
    }
    window.addEventListener("focus", onFocus)
    chrome.storage.onChanged.addListener(onAuth)
    return () => {
      window.removeEventListener("focus", onFocus)
      chrome.storage.onChanged.removeListener(onAuth)
    }
  }, [load])

  React.useEffect(() => {
    if (!notice) return
    const t = window.setTimeout(() => setNotice(null), 5000)
    return () => window.clearTimeout(t)
  }, [notice])

  const setPrefs = (prefs: Prefs) => {
    setStatus((s) => (s ? { ...s, prefs } : s))
    void send({ type: "prefs", prefs })
  }

  const fill = async () => {
    if (!tabId) return
    setBusy(true)
    setError(null)
    try {
      const result = await send<Review>({ type: "fill", tabId })
      setStatus((s) => (s?.me && result.remainingToday !== null ? { ...s, me: { ...s.me, drafting: { ...s.me.drafting, remaining_today: result.remainingToday } } } : s))
    } catch (err) {
      const message = err instanceof Error ? err.message : "Couldn't fill this page"
      setError(message)
      if (/not connected/i.test(message)) void load()
    } finally {
      setBusy(false)
    }
  }

  const appUrl = status?.settings.appUrl ?? ""
  const me = status?.me
  const moved = review?.moved ?? null
  const projectChosen = !!me?.projects.some((p) => p.id === status?.prefs.fillAs)

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 flex items-center gap-2.5 border-b border-separator bg-canvas/95 px-4 py-2.5 backdrop-blur">
        <Logo className="size-6" title="" />
        <div className="min-w-0 flex-1">
          <p className="text-callout font-semibold text-ink">Blesser</p>
          {me ? <p className="truncate text-[12px] leading-4 text-ink-secondary">{me.user.display_name || me.user.email}</p> : null}
        </div>
        <Button size="sm" variant="quiet" iconOnly icon={<SettingsIcon />} aria-label="Extension options" title="Extension options" className="size-8 [&_svg]:size-4" onClick={() => void chrome.runtime.openOptionsPage()} />
        {status?.connected ? (
          <Button
            size="sm"
            variant="quiet"
            iconOnly
            icon={<LogOut />}
            aria-label="Disconnect this browser"
            title="Disconnect this browser"
            className="size-8 [&_svg]:size-4"
            onClick={async () => {
              await send({ type: "disconnect" })
              void load()
            }}
          />
        ) : null}
      </header>

      <main className="flex-1 space-y-4 px-4 py-4">
        {!status ? (
          <div className="space-y-2" aria-busy="true">
            <div className="h-10 animate-pulse rounded-md bg-surface-sunk" />
            <div className="h-10 animate-pulse rounded-md bg-surface-sunk" />
          </div>
        ) : !status.connected ? (
          <section className="space-y-3 pt-2">
            <h1 className="type-title-3 text-ink">Fill forms from your Apply kit</h1>
            <p className="text-callout text-ink-secondary">
              Connect this browser to Blesser. You'll confirm in the Blesser app; your password never enters the extension.
            </p>
            <Button variant="brand" className="w-full" onClick={() => void send({ type: "connect" })}>
              Connect to Blesser
            </Button>
          </section>
        ) : !me ? (
          <section className="space-y-3">
            <p role="alert" className="text-callout text-ink">{status.error ?? "Blesser didn't answer."}</p>
            <Button size="sm" variant="secondary" onClick={() => void load()}>Try again</Button>
          </section>
        ) : (
          <>
            <section aria-label="Fill settings" className="divide-y divide-separator rounded-md border border-separator bg-surface">
              <label className="flex items-center gap-3 px-3 py-2">
                <span className="w-16 shrink-0 text-footnote font-medium text-ink-secondary">Fill as</span>
                <Select
                  value={projectChosen ? status.prefs.fillAs : "me"}
                  onChange={(e) => setPrefs({ ...status.prefs, fillAs: e.target.value })}
                  className="h-8 min-w-0 flex-1 px-2.5 pr-9 text-footnote"
                >
                  <option value="me">Me</option>
                  {me.projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </Select>
              </label>
              <div className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-footnote font-medium text-ink">
                    <Sparkles className="size-3.5 text-caution" aria-hidden="true" /> Draft answers I haven't saved
                  </p>
                  <p className="text-[12px] leading-4 text-ink-tertiary">
                    {me.drafting.enabled ? `${me.drafting.remaining_today} left today. You review every draft.` : "Drafting is off on this Blesser."}
                  </p>
                </div>
                <Switch
                  label="Draft answers I haven't saved"
                  disabled={!me.drafting.enabled}
                  checked={status.prefs.allowDrafting && me.drafting.enabled}
                  onChange={(allowDrafting) => setPrefs({ ...status.prefs, allowDrafting })}
                />
              </div>
            </section>
            {projectChosen ? <p className="-mt-2 text-[12px] leading-4 text-ink-tertiary">Personal questions still use your profile.</p> : null}

            {moved ? <Moved moved={moved} /> : null}

            <div className="space-y-1.5">
              <Button variant="primary" className="w-full" disabled={busy || !tabId} onClick={() => void fill()}>
                {busy ? "Filling…" : moved ? "Fill this step" : "Fill this page"}
              </Button>
              <p className="text-center text-[12px] leading-4 text-ink-tertiary">Blesser never submits. You check and send.</p>
            </div>

            {error ? <p role="alert" className="rounded-md bg-critical-soft px-3 py-2 text-footnote text-critical">{error}</p> : null}

            {review && tabId ? (
              <section aria-label="Results" className="space-y-3">
                <Summary review={review} />
                {counts(review).drafted ? (
                  <p className="text-[12px] leading-4 text-ink-tertiary">Drafted answers have a dashed outline on the page. Read them before you submit.</p>
                ) : null}
                <ReviewList key={review.at} review={review} tabId={tabId} stale={!!moved} />
                <Applied review={review} tabId={tabId} />
              </section>
            ) : null}
          </>
        )}
      </main>

      {status?.connected ? (
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-separator px-4 py-2.5">
          {notice ? (
            <p role="status" className="flex items-center gap-1.5 text-footnote text-positive">
              <Check className="size-3.5" aria-hidden="true" /> {notice}
            </p>
          ) : (
            <button
              type="button"
              disabled={!tabId}
              onClick={() => setReporting(true)}
              className="inline-flex cursor-pointer items-center gap-1 rounded-sm text-footnote font-medium text-ink-secondary hover:text-ink focus-visible:outline-2 focus-visible:outline-focus disabled:opacity-50"
            >
              <Flag className="size-3.5" aria-hidden="true" /> Report a problem
            </button>
          )}
          <a href={`${appUrl}/kit`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-sm text-footnote font-medium text-link focus-visible:outline-2 focus-visible:outline-focus">
            Apply kit <ArrowUpRight className="size-3.5" aria-hidden="true" />
          </a>
        </footer>
      ) : null}

      {tabId ? (
        <ReportDialog
          tabId={tabId}
          open={reporting}
          onClose={() => setReporting(false)}
          onSent={() => {
            setReporting(false)
            setNotice("Thanks. Your report was sent.")
          }}
        />
      ) : null}
    </div>
  )
}

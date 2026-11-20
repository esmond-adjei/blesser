import * as React from "react"
import { ArrowUpRight, Check, Flag, Footprints, LogOut, Settings as SettingsIcon, Sparkles, WandSparkles } from "lucide-react"
import { Button, Logo, Select, Wordmark, cn } from "@blesser/ui"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../../../webapp/src/components/ui/menu"
import type { Prefs, Review, Status } from "../shared/types"
import { FILL_REQUEST, send } from "../shared/ui"
import { FormProgressCard } from "./FormProgress"
import { Opportunity } from "./Opportunity"
import { ReportDialog } from "./ReportDialog"
import { ReviewList } from "./ReviewList"
import { useFormProgress } from "./useFormProgress"
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

function Moved({ moved }: { moved: NonNullable<Review["moved"]> }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-info-soft px-3 py-2" role="status">
      <Footprints className="mt-0.5 size-4 shrink-0 text-info" aria-hidden="true" />
      <p className="text-footnote text-ink">
        {moved === "navigated" ? "You're on a new page or step." : "New fields appeared on this page."} Fill this step when you're ready. The list shows fields from the previous fill.
      </p>
    </div>
  )
}

export function Panel() {
  const [status, setStatus] = React.useState<Status | null>(null)
  const { tabId, pageTitle, review } = usePanelTab()
  const progress = useFormProgress(tabId, review?.at ?? null)
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

  const fillRef = React.useRef(fill)
  React.useEffect(() => {
    fillRef.current = fill
  })

  React.useEffect(() => {
    if (!tabId || !status?.me) return
    const take = (request: unknown) => {
      const r = request as { tabId?: number; at?: number } | undefined
      if (r?.tabId !== tabId || !r.at || Date.now() - r.at > 15_000) return
      void chrome.storage.session.remove(FILL_REQUEST)
      void fillRef.current()
    }
    void chrome.storage.session.get(FILL_REQUEST).then((stored) => take(stored[FILL_REQUEST]))
    const onChanged = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === "session" && changes[FILL_REQUEST]?.newValue) take(changes[FILL_REQUEST].newValue)
    }
    chrome.storage.onChanged.addListener(onChanged)
    return () => chrome.storage.onChanged.removeListener(onChanged)
  }, [tabId, status?.me])

  const allowEverywhere = async () => {
    if (await chrome.permissions.request({ origins: ["https://*/*", "http://*/*"] })) void fill()
  }

  const me = status?.me
  const moved = review?.moved ?? null
  const currentReview = moved === "navigated" ? null : review
  const projectChosen = !!me?.projects.some((p) => p.id === status?.prefs.fillAs)
  const filledCount = review?.rows.filter((row) => row.filled).length ?? 0
  const fillLabel = moved ? "Fill this step" : filledCount ? `Fill ${filledCount} ${filledCount === 1 ? "field" : "fields"}` : "Fill this page"
  const accountActions: MenuAction[] = [
    { label: "Extension options", icon: <SettingsIcon />, onSelect: () => void chrome.runtime.openOptionsPage() },
  ]
  if (status?.connected) {
    accountActions.push(
      { label: "Apply kit", icon: <ArrowUpRight />, href: `${status.settings.appUrl}/kit` },
      { label: "Report a problem", icon: <Flag />, disabled: !tabId, onSelect: () => setReporting(true) },
      { kind: "separator" },
      {
        label: "Disconnect this browser",
        icon: <LogOut />,
        onSelect: async () => {
          await send({ type: "disconnect" })
          void load()
        },
      },
    )
  }

  return (
    <div className="min-h-dvh">
      <ActionContextMenu actions={accountActions}>
        <header className="sticky top-0 z-20 border-b border-separator bg-canvas">
          <div className="mx-auto flex max-w-reading items-center justify-between gap-3 px-4 py-3">
            <div className="flex shrink-0 items-center gap-1.5">
              <Logo className="size-[22px]" title="" />
              <Wordmark className="text-[22px]" />
            </div>
            <div className="flex min-w-0 items-center gap-1.5">
              {me ? <p className="truncate text-right text-footnote text-ink-secondary" title={me.user.display_name || me.user.email}>{me.user.display_name || me.user.email}</p> : null}
              <ActionMenuButton actions={accountActions} label={me ? "Account actions" : "Extension actions"} />
            </div>
          </div>
        </header>
      </ActionContextMenu>

      <main className="mx-auto max-w-reading space-y-3 p-4">
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
            <Opportunity key={`${tabId}:${currentReview?.matchedOpportunityId ?? ""}`} tabId={tabId} pageTitle={pageTitle} review={currentReview} />

            {progress && tabId ? <FormProgressCard tabId={tabId} progress={progress} onSaved={(name) => setNotice(`Saved ${name}`)} /> : null}

            <section aria-labelledby="fill-title" aria-busy={busy} className="bl-enter space-y-4 rounded-lg border border-separator bg-surface p-3.5 [--i:2]">
              <h2 id="fill-title" className="type-title-3 text-ink">Fill this form</h2>
              <div className="divide-y divide-separator rounded-md bg-surface-sunk">
                <label className="flex items-center gap-3 px-3 py-2">
                  <span className="shrink-0 text-footnote font-medium text-ink-secondary">Fill as</span>
                  <Select
                    value={projectChosen ? status.prefs.fillAs : "me"}
                    onChange={(e) => setPrefs({ ...status.prefs, fillAs: e.target.value })}
                    className="h-control-sm min-w-0 flex-1 px-2.5 pr-9 text-footnote"
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
                      <Sparkles className="size-3.5 shrink-0 text-caution" aria-hidden="true" /> Draft answers I haven't saved
                    </p>
                    <p className="text-caption text-ink-tertiary">
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
              </div>
              {projectChosen ? <p className="text-caption text-ink-tertiary">Personal questions still use your profile.</p> : null}
              {moved ? <Moved moved={moved} /> : null}
              {review && tabId && (
                <>
                  {review.rows.some((row) => row.status === "drafted") ? (
                    <p className="text-caption text-ink-tertiary">Drafted answers have a dashed outline on the page. Read them before you submit.</p>
                  ) : null}
                  <ReviewList key={review.at} review={review} tabId={tabId} stale={!!moved} />
                </>
              )}
              <Button variant="primary" icon={<WandSparkles aria-hidden="true" />} className="w-full" disabled={busy || !tabId} onClick={() => void fill()} title={!moved && filledCount ? "Based on the last fill" : undefined}>
                {busy ? "Filling…" : fillLabel}
              </Button>
              {error ? <p role="alert" className="rounded-md bg-critical-soft px-3 py-2 text-footnote text-critical">{error}</p> : null}
              {error?.startsWith("Chrome hasn't let Blesser") ? (
                <div className="space-y-1.5 rounded-md bg-surface-sunk px-3 py-2.5">
                  <p className="text-footnote text-ink-secondary">
                    You can let Blesser read form pages on any site. It still only fills when you ask. You can turn this off in Chrome's extension settings.
                  </p>
                  <Button variant="secondary" className="w-full" onClick={() => void allowEverywhere()}>
                    Allow on all sites
                  </Button>
                </div>
              ) : null}
            </section>
            <p className="px-2 text-center text-footnote text-ink-tertiary">Review every field before you send.</p>
          </>
        )}
        {notice ? (
          <p role="status" className="flex items-center gap-1.5 text-footnote text-positive">
            <Check className="size-3.5" aria-hidden="true" /> {notice}
          </p>
        ) : null}
      </main>

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

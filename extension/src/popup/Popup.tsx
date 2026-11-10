import * as React from "react"
import { ArrowUpRight, Check, ChevronDown, CornerDownRight, LogOut, Settings as SettingsIcon, Sparkles } from "lucide-react"
import { Button, Logo, Select, cn } from "@blesser/ui"
import type { FillSummary, Prefs, Status } from "../shared/types"
import { send } from "../shared/ui"

async function targetTab(): Promise<number | null> {
  if (__TEST_BUILD__) {
    const forced = Number(new URLSearchParams(location.search).get("tab"))
    if (forced) return forced
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab?.id ?? null
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (next: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn("relative h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors duration-160", checked ? "bg-forest" : "bg-control-border")}
    >
      <span className={cn("absolute top-0.5 size-4 rounded-full bg-surface shadow-elevation-1 transition-all", checked ? "left-[18px]" : "left-0.5")} />
    </button>
  )
}

function Stat({ value, label, tone }: { value: number; label: string; tone: "positive" | "caution" | "ink" }) {
  return (
    <div className="flex-1 rounded-md bg-surface-sunk px-2.5 py-2">
      <p className={cn("type-title-3 tabular-nums", tone === "positive" ? "text-positive" : tone === "caution" ? "text-caution" : "text-ink")}>{value}</p>
      <p className="text-footnote leading-tight text-ink-secondary">{label}</p>
    </div>
  )
}

function Results({ summary, tabId, onApplied }: { summary: FillSummary; tabId: number; onApplied: (next: FillSummary) => void }) {
  const [open, setOpen] = React.useState(false)
  const [marking, setMarking] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const left = summary.needsYou.length

  return (
    <section aria-label="Results" className="space-y-3 rounded-lg border border-separator bg-surface p-3">
      <div className="flex gap-2">
        <Stat value={summary.filled} label="filled" tone="positive" />
        <Stat value={summary.drafted} label="drafted for review" tone="caution" />
        <Stat value={left} label={left === 1 ? "needs you" : "need you"} tone="ink" />
      </div>
      {summary.drafted ? (
        <p className="text-footnote text-ink-secondary">Drafted answers have a dashed outline. Read them before you submit.</p>
      ) : null}
      {left ? (
        <div>
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex items-center gap-1 text-callout font-medium text-link">
            <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden="true" />
            {open ? "Hide what's left" : "Show what's left"}
          </button>
          {open ? (
            <ul className="mt-2 max-h-44 space-y-1 overflow-y-auto">
              {summary.needsYou.map((item) => (
                <li key={item.key}>
                  <button
                    type="button"
                    onClick={() => void send({ type: "focus", tabId, key: item.key }).catch(() => {})}
                    className="flex w-full items-start gap-2 rounded-sm px-1.5 py-1 text-left hover:bg-surface-sunk"
                  >
                    <CornerDownRight className="mt-0.5 size-3.5 shrink-0 text-ink-tertiary" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block truncate text-callout text-ink">{item.label}</span>
                      <span className="block text-footnote text-ink-secondary">{item.reason}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {summary.matchedOpportunityId ? (
        summary.applied ? (
          <p className="flex items-center gap-1.5 text-callout text-positive"><Check className="size-4" aria-hidden="true" /> Marked as applied</p>
        ) : (
          <div className="flex items-center justify-between gap-2 border-t border-separator pt-3">
            <p className="text-footnote text-ink-secondary">You track this one. Submitted it?</p>
            <Button
              size="sm"
              variant="secondary"
              disabled={marking}
              onClick={async () => {
                setMarking(true)
                setError(null)
                try {
                  onApplied(await send<FillSummary>({ type: "markApplied", tabId }))
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
        )
      ) : null}
      {error ? <p role="alert" className="text-footnote text-critical">{error}</p> : null}
    </section>
  )
}

export function Popup() {
  const [status, setStatus] = React.useState<Status | null>(null)
  const [tabId, setTabId] = React.useState<number | null>(null)
  const [summary, setSummary] = React.useState<FillSummary | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    try {
      const [next, tab] = await Promise.all([send<Status>({ type: "status" }), targetTab()])
      if (next.me && next.prefs.fillAs !== "me" && !next.me.projects.some((p) => p.id === next.prefs.fillAs)) {
        next.prefs = { ...next.prefs, fillAs: "me" }
        void send({ type: "prefs", prefs: next.prefs })
      }
      setStatus(next)
      setTabId(tab)
      if (tab) setSummary(await send<FillSummary | null>({ type: "lastResult", tabId: tab }))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load")
    }
  }, [])

  React.useEffect(() => {
    void load()
    const onFocus = () => void load()
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [load])

  const setPrefs = (prefs: Prefs) => {
    setStatus((s) => (s ? { ...s, prefs } : s))
    void send({ type: "prefs", prefs })
  }

  const fill = async () => {
    if (!tabId) return
    setBusy(true)
    setError(null)
    try {
      const result = await send<FillSummary>({ type: "fill", tabId })
      setSummary(result)
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

  return (
    <div className="w-[360px] space-y-4 p-4">
      <header className="flex items-center gap-2.5">
        <Logo className="size-7" title="" />
        <div className="min-w-0 flex-1">
          <p className="text-callout font-semibold text-ink">Blesser</p>
          {me ? <p className="truncate text-footnote text-ink-secondary">{me.user.display_name || me.user.email}</p> : null}
        </div>
        <Button size="sm" variant="quiet" iconOnly icon={<SettingsIcon />} aria-label="Extension options" onClick={() => void chrome.runtime.openOptionsPage()} />
        {status?.connected ? (
          <Button
            size="sm"
            variant="quiet"
            iconOnly
            icon={<LogOut />}
            aria-label="Disconnect this browser"
            title="Disconnect this browser"
            onClick={async () => {
              await send({ type: "disconnect" })
              setSummary(null)
              void load()
            }}
          />
        ) : null}
      </header>

      {!status ? (
        <div className="space-y-2" aria-busy="true">
          <div className="h-10 animate-pulse rounded-md bg-surface-sunk" />
          <div className="h-10 animate-pulse rounded-md bg-surface-sunk" />
        </div>
      ) : !status.connected ? (
        <section className="space-y-3">
          <h1 className="type-title-3 text-ink">Fill forms from your Apply kit</h1>
          <p className="text-callout text-ink-secondary">
            Connect this browser to Blesser. You'll confirm in the Blesser app; your password never enters the extension.
          </p>
          <Button variant="brand" className="w-full" onClick={() => void send({ type: "connect" }).then(() => window.close())}>
            Connect to Blesser
          </Button>
        </section>
      ) : !me ? (
        <section className="space-y-3">
          <p role="alert" className="text-callout text-ink">{status.error ?? "Blesser didn't answer."}</p>
          <Button size="sm" variant="secondary" onClick={() => void load()}>Try again</Button>
        </section>
      ) : (
        <section className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-footnote font-medium text-ink-secondary">Fill as</span>
            <Select value={me.projects.some((p) => p.id === status.prefs.fillAs) ? status.prefs.fillAs : "me"} onChange={(e) => setPrefs({ ...status.prefs, fillAs: e.target.value })} className="h-control-sm text-callout">
              <option value="me">Me</option>
              {me.projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </Select>
            {me.projects.some((p) => p.id === status.prefs.fillAs) ? <span className="mt-1 block text-footnote text-ink-tertiary">Personal questions still use your profile.</span> : null}
          </label>
          <div className="flex items-center justify-between gap-3 rounded-md border border-separator bg-surface px-3 py-2.5">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-callout font-medium text-ink"><Sparkles className="size-3.5 text-caution" aria-hidden="true" /> Draft answers I haven't saved</p>
              <p className="text-footnote text-ink-secondary">
                {me.drafting.enabled ? `${me.drafting.remaining_today} left today. You review every draft.` : "Drafting is off on this Blesser."}
              </p>
            </div>
            <Switch
              label="Draft answers I haven't saved"
              checked={status.prefs.allowDrafting && me.drafting.enabled}
              onChange={(allowDrafting) => setPrefs({ ...status.prefs, allowDrafting })}
            />
          </div>
          <Button variant="primary" className="w-full" disabled={busy || !tabId} onClick={() => void fill()}>
            {busy ? "Filling…" : "Fill this page"}
          </Button>
          <p className="text-center text-footnote text-ink-tertiary">Blesser never submits. You check and send.</p>
          {summary && tabId ? <Results summary={summary} tabId={tabId} onApplied={setSummary} /> : null}
        </section>
      )}

      {error ? <p role="alert" className="text-callout text-critical">{error}</p> : null}

      {status?.connected ? (
        <a href={`${appUrl}/kit`} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-footnote font-medium text-link">
          Fill gaps in your Apply kit <ArrowUpRight className="size-3.5" aria-hidden="true" />
        </a>
      ) : null}
    </div>
  )
}

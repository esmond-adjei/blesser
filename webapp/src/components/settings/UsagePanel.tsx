import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Link, useLocation } from "react-router-dom"
import * as api from "../../lib/api"
import { cn } from "../../lib/utils"
import { Skeleton, SkeletonStack } from "../ui/feedback"
import { SegmentedControl } from "../ui/form"
import { fmt } from "../../lib/format"
import { SettingsPanel } from "./controls"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { BarList, Section, Stat, Swatch } from "../charts/StatParts"
import { TICK, TOOLTIP } from "../charts/chartStyle"

const RANGES = [7, 30, 90].map((d) => ({ value: d, label: `${d}d` }))

/** Features in a fixed order, each with its fixed series colour. */
const FEATURES = [
  { id: "research", label: "Research runs", color: "var(--chart-1)" },
  { id: "chat", label: "Gradis chat", color: "var(--chart-2)" },
  { id: "suggestions", label: "Document suggestions", color: "var(--chart-3)" },
  { id: "cv_edits", label: "Document editor", color: "var(--chart-4)" },
  { id: "other", label: "Other activity", color: "var(--chart-5)" },
]
const featureOf = (id: string) => FEATURES.find((f) => f.id === id) ?? FEATURES[FEATURES.length - 1]

const dayLabel = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })

/** Change against the period before, in words. */
function change(now: number, before: number, days: number): string {
  if (before === 0) return now === 0 ? "No use yet" : `New vs prior ${days}d`
  const pct = Math.round(((now - before) / before) * 100)
  if (pct === 0) return `Flat vs prior ${days}d`
  return `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}% vs prior ${days}d`
}

/** Tokens per day, stacked by feature. */
function DailyChart({ data }: { data: api.AccountUsage }) {
  const shown = FEATURES.filter((f) => data.by_day_feature.some((r) => featureOf(r.feature).id === f.id && r.tokens > 0))
  const rows = data.days.map((d) => {
    const row: Record<string, number | string> = { day: d.day }
    for (const f of shown) row[f.id] = 0
    for (const r of data.by_day_feature) if (r.day === d.day && r.tokens > 0) row[featureOf(r.feature).id] = Number(row[featureOf(r.feature).id] ?? 0) + r.tokens
    return row
  })
  const totals = Object.fromEntries(shown.map((f) => [f.id, rows.reduce((n, r) => n + Number(r[f.id] ?? 0), 0)]))
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-x-4 gap-y-1 type-caption">
        {shown.map((f) => <Swatch key={f.id} color={f.color} label={`${f.label} ${fmt(totals[f.id])}`} />)}
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={rows} margin={{ top: 4, right: 0, bottom: 0, left: 0 }} barCategoryGap="20%">
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="0" />
          <XAxis dataKey="day" tickFormatter={dayLabel} tick={TICK} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tickFormatter={(v) => fmt(Number(v))} tick={TICK} tickLine={false} axisLine={false} width={44} />
          <Tooltip {...TOOLTIP} labelFormatter={(d) => dayLabel(String(d))} formatter={(v, name) => [`${fmt(Number(v))} tokens`, featureOf(String(name)).label]} />
          {shown.map((f, i) => (
            <Bar
              key={f.id}
              dataKey={f.id}
              stackId="tokens"
              fill={f.color}
              stroke="var(--card)"
              strokeWidth={1}
              radius={i === shown.length - 1 ? [4, 4, 0, 0] : undefined}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Your plan: what's included and this month's use against its limits. */
function PlanCard() {
  const [plan, setPlan] = React.useState<api.PlanSummary | null>(null)
  const [switching, setSwitching] = React.useState(false)
  const queryClient = useQueryClient()
  const location = useLocation()
  React.useEffect(() => {
    let cancelled = false
    api.getPlan().then((p) => !cancelled && setPlan(p)).catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])
  if (!plan) return <Skeleton className="h-28" />

  function pick(id: string) {
    setSwitching(true)
    api
      .switchPlan(id)
      .then((p) => {
        setPlan(p)
        // The sidebar, run form and model picker read the plan too.
        queryClient.setQueryData(["plan"], p)
      })
      .catch(() => {})
      .finally(() => setSwitching(false))
  }
  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-semibold">
          {plan.plan.label} plan
          {!plan.enforced && (
            <span className="ml-2 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              Everything included during beta
            </span>
          )}
        </p>
        <div className="flex items-center gap-3">
          {plan.quotas.some((q) => q.limit != null) && (
            <p className="type-caption">Limits reset on the 1st of each month</p>
          )}
          {plan.enforced && (
            <Link
              to={`/plans?next=${encodeURIComponent(location.pathname + location.search)}`}
              className="text-xs font-medium text-primary hover:underline"
            >
              Change plan
            </Link>
          )}
        </div>
      </div>
      {plan.switchable && (
        <label className="mt-3 flex flex-wrap items-center gap-2 type-caption">
          <span className="rounded-full bg-caution-soft px-2 py-0.5 font-medium text-caution">Dev</span>
          Switch plan to try its limits
          <select
            value={plan.plan.id}
            disabled={switching}
            onChange={(e) => pick(e.target.value)}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
          >
            {plan.plans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        {plan.quotas.map((q) => {
          const pct = q.limit && q.used != null ? Math.min(100, Math.round((q.used / q.limit) * 100)) : 0
          return (
            <div key={q.key}>
              <p className="type-caption">{q.label}</p>
              <p className="mt-0.5 text-sm font-medium tabular-nums">
                {q.limit == null
                  ? q.used != null
                    ? `${fmt(q.used)} used, no limit`
                    : "No limit"
                  : q.used != null
                    ? `${fmt(q.used)} of ${fmt(q.limit)}`
                    : `Up to ${fmt(q.limit)}`}
              </p>
              {q.used != null && q.limit != null && (
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
                  <div className={cn("h-full rounded-full", pct >= 100 ? "bg-caution" : "bg-primary/70")} style={{ width: `${pct}%` }} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

export function UsagePanel() {
  const [days, setDays] = React.useState(30)
  // Key results by range, so switching shows the skeleton until data lands.
  const [loaded, setLoaded] = React.useState<{ days: number; data: api.AccountUsage } | null>(null)
  const [error, setError] = React.useState(false)
  const data = loaded?.days === days ? loaded.data : null

  React.useEffect(() => {
    let cancelled = false
    api
      .getAccountUsage(days)
      .then((d) => !cancelled && setLoaded({ days, data: d }))
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
    }
  }, [days])

  return (
    <SettingsPanel title="Usage" description="Your plan, and how much AI work your account has done."
      action={<SegmentedControl label="Time range" value={days} onChange={(next) => { setError(false); setDays(next) }} options={RANGES} />}>
      {error ? (
        <p className="mt-6 text-sm text-destructive">Couldn't load usage.</p>
      ) : !data ? (
        <SkeletonStack className="mt-6 space-y-3" blocks={["h-28", "h-16", "h-48"]} />
      ) : (
        <div className="mt-6 space-y-6">
          <PlanCard />
          <UsageReport data={data} days={days} />
        </div>
      )}
    </SettingsPanel>
  )
}

function UsageReport({ data, days }: { data: api.AccountUsage; days: number }) {
  const tokens = data.totals.input_tokens + data.totals.output_tokens
  const before = data.previous.input_tokens + data.previous.output_tokens
  const active = data.days.filter((d) => d.calls > 0)
  const busiest = data.days.reduce((a, b) => (b.input_tokens + b.output_tokens > a.input_tokens + a.output_tokens ? b : a), data.days[0])
  const scoring = data.by_feature.filter((r) => r.feature === "scoring").reduce((n, r) => n + r.calls, 0)

  const byFeature = FEATURES.map((f) => ({
    label: f.label,
    fill: f.color,
    value: data.by_feature.filter((r) => featureOf(r.feature).id === f.id && r.feature !== "scoring").reduce((n, r) => n + r.input_tokens + r.output_tokens, 0),
  })).filter((r) => r.value > 0)

  const models = new Map<string, number>()
  for (const r of data.by_feature) {
    if (r.feature === "scoring") continue
    const name = r.model && r.model !== "unknown" ? r.model : r.provider
    models.set(name, (models.get(name) ?? 0) + r.input_tokens + r.output_tokens)
  }
  const byModel = [...models].map(([label, value]) => ({ label, value, fill: "var(--chart-1)" })).filter((r) => r.value > 0).sort((a, b) => b.value - a.value)

  const perDay = active.length ? Math.round(data.totals.calls / active.length) : 0
  const writtenPct = tokens ? Math.round((data.totals.output_tokens / tokens) * 100) : 0
  const hints = {
    tokens: [
      `${fmt(tokens)} means your runs, Gradis and other features read and wrote about ${tokens.toLocaleString()} tokens of text in the last ${days} days (${fmt(data.totals.input_tokens)} read, ${fmt(data.totals.output_tokens)} written).`,
      before > 0
        ? `The prior ${days} days used ${fmt(before)}, which the arrow compares against.`
        : tokens > 0 && `There was no use in the ${days} days before, so there's nothing to compare against.`,
    ],
    calls: [
      `${fmt(data.totals.calls)} is how many times a model was asked for a reply in the last ${days} days. One agent step is usually one call.`,
      perDay > 0 && `"${fmt(perDay)} per active day" averages that over the days with any use, not all ${days}.`,
    ],
    days: [
      `${active.length} of ${days} means you used a model on ${active.length} of the last ${days} days.`,
      active.length > 0 && `The busiest was ${dayLabel(busiest.day)}, with ${fmt(busiest.input_tokens + busiest.output_tokens)} tokens.`,
    ],
    written: [
      `${fmt(data.totals.output_tokens)} is the text models wrote back, such as replies, drafts and saved findings. The rest of the tokens are what they read.`,
      tokens > 0 && `${writtenPct}% of all tokens means writing was ${writtenPct < 20 ? "a small share; most of the work was reading pages and context" : "a large share of the work"}.`,
    ],
  }
  const hint = (lines: (string | false)[]) => lines.filter(Boolean).join(" ")

  return (
    <>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Tokens" value={fmt(tokens)} detail={change(tokens, before, days)} hint={hint(hints.tokens)} />
        <Stat label="Model calls" value={fmt(data.totals.calls)} detail={perDay ? `${fmt(perDay)} per active day` : "No calls yet"} hint={hint(hints.calls)} />
        <Stat label="Active days" value={`${active.length} of ${days}`} detail={active.length ? `Busiest ${dayLabel(busiest.day)}` : "No activity yet"} hint={hint(hints.days)} />
        <Stat label="Written by models" value={fmt(data.totals.output_tokens)} detail={tokens ? `${writtenPct}% of all tokens` : "Output tokens"} hint={hint(hints.written)} />
      </dl>

      {data.totals.calls === 0 ? (
        <p className="type-meta">No model usage in the last {days} days.</p>
      ) : (
        <>
          <Section title="Tokens per day">
            <DailyChart data={data} />
          </Section>

          <div className="grid gap-6 sm:grid-cols-2">
            {byFeature.length > 0 && (
              <Section title="By feature">
                <BarList rows={byFeature} unit="tokens" format={fmt} />
              </Section>
            )}
            {byModel.length > 0 && (
              <Section title="By model">
                <BarList rows={byModel} unit="tokens" format={fmt} />
              </Section>
            )}
          </div>
          {scoring > 0 && <p className="type-caption">Fit scoring also made {fmt(scoring)} embedding call{scoring === 1 ? "" : "s"}; most embedding providers don't report tokens.</p>}

          <Section title="Every feature and model">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="text-left type-caption">
                  <th className="py-2 font-normal">Feature</th>
                  <th className="py-2 font-normal">Model</th>
                  <th className="py-2 text-right font-normal">Calls</th>
                  <th className="py-2 text-right font-normal">Read</th>
                  <th className="py-2 text-right font-normal">Written</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {data.by_feature.map((row) => (
                  <tr key={`${row.feature}:${row.provider}:${row.model}`}>
                    <td className="py-2 pr-3">{row.feature === "scoring" ? "Fit scoring" : featureOf(row.feature).label}</td>
                    <td className="max-w-40 truncate py-2 pr-3 text-muted-foreground" title={row.model}>{row.model && row.model !== "unknown" ? row.model : row.provider}</td>
                    <td className="py-2 text-right">{row.calls.toLocaleString()}</td>
                    <td className="py-2 text-right">{row.feature === "scoring" ? "–" : fmt(row.input_tokens)}</td>
                    <td className="py-2 text-right">{row.feature === "scoring" ? "–" : fmt(row.output_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </>
      )}
    </>
  )
}

import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { BarList, LABEL_WIDTH, ROW_HEIGHT, Section, Stat, Swatch, Tick } from "../charts/StatParts"
import { TICK, TOOLTIP } from "../charts/chartStyle"
import { fmt, formatDuration } from "../../lib/format"
import { useRun, useRunRefusals, useRunUsage } from "../../lib/queries"
import type { Usage } from "../../lib/types"
import { Alert, AlertDescription, Skeleton } from "../ui/feedback"

/** Why a professor task took the full agent loop. */
const FALLBACK_LABELS: Record<string, string> = {
  application_indexing: "Also indexed the programme's admissions",
  resume: "Resumed from a checkpoint",
  user_added: "Added by you",
  pipeline_off: "Code-first pass switched off",
  no_author_at_school: "No OpenAlex author at the school",
  multiple_authors: "Several OpenAlex authors at the school",
  openalex_unavailable: "OpenAlex unavailable",
  no_recent_works: "No recent works",
  scoring_failed: "Scoring failed",
  no_match_refused: "No-match not recorded",
  unknown: "Other",
}

/** Tools shown before the rest fold into "Other". */
const TOOL_ROWS = 6

export function UsageTab({ runId }: { runId: string }) {
  const { data, isLoading, isError } = useRunUsage(runId)
  const { data: refusals } = useRunRefusals(runId)
  const { data: run } = useRun(runId)
  if (isLoading)
    return (
      <div aria-label="Loading stats" aria-busy="true" className="space-y-3">
        <div className="grid grid-cols-2 gap-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-16" />)}</div>
        <Skeleton className="h-40" />
      </div>
    )
  if (isError || !data)
    return (
      <Alert variant="destructive">
        <AlertDescription>Couldn't load stats for this run.</AlertDescription>
      </Alert>
    )

  const researched = refusals?.researched ?? 0
  const saved = refusals?.saved ?? data.candidates ?? 0
  const tokens = data.input_tokens + data.output_tokens
  const toolCalls = Object.values(data.tools ?? {}).reduce((n, t) => n + t.calls, 0)
  const models = (data.models ?? []).map((m) => m.model).filter(Boolean).join(", ")
  const first = data.first_candidate_seconds
  const live = run ? !run.finished_at : false
  const runTime = formatDuration(data.active_seconds ?? 0)
  const hints = {
    matches: [
      researched
        ? `${saved} of ${researched} means ${saved} of the ${researched} professors this run researched were saved as matches; the breakdown below says why the rest weren't.`
        : `${saved} professors were saved as matches.`,
    ],
    first: [
      first != null
        ? `${formatDuration(first)} is how long after the run started its first professor was saved as a match: how quickly the run began paying off.`
        : "No professor has been saved as a match yet; this shows how long the first one took once it is.",
    ],
    runTime: [
      `${runTime} is how long the run's agents were at work on the clock${live ? " so far (it's still going)" : ""}. Tasks running at the same time count once, and idle gaps, like a task rerun days later, don't count.`,
      `In that time its agents made ${data.turns.toLocaleString()} model calls and ${toolCalls.toLocaleString()} lookups such as web searches, page reads and OpenAlex.`,
    ],
    tokens: [
      `${fmt(tokens)} means the run's agents read and wrote about ${tokens.toLocaleString()} tokens of text in total (${fmt(data.input_tokens)} read, ${fmt(data.output_tokens)} written).`,
      data.tokens_per_candidate != null &&
        `"${fmt(data.tokens_per_candidate)} per match" is that total divided by the matches saved: roughly what each match cost.`,
      models && `Models used: ${models}.`,
    ],
  }
  const hint = (lines: (string | false)[]) => lines.filter(Boolean).join(" ")
  const outcomes = [
    { label: "Saved as matches", value: saved, fill: "var(--chart-1)" },
    ...(refusals?.not_saved ?? []).map((r) => ({ label: r.label, value: r.count, fill: "var(--chart-rest)" })),
  ].filter((r) => r.value > 0)

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-2">
        <Stat
          label="Matches"
          hint={hint(hints.matches)}
          value={researched ? `${saved} of ${researched}` : String(saved)}
          detail={researched ? `${Math.round((saved / researched) * 100)}% of researched professors` : "saved as matches"}
        />
        <Stat
          label="First match"
          hint={hint(hints.first)}
          value={first != null ? formatDuration(first) : "None yet"}
          detail={first != null ? "after the run started" : live ? "still looking" : "no match saved"}
        />
        <Stat
          label="Run time"
          hint={hint(hints.runTime)}
          value={runTime}
          detail={`${data.turns.toLocaleString()} model calls`}
        />
        <Stat
          label="Tokens"
          hint={hint(hints.tokens)}
          value={fmt(tokens)}
          detail={data.tokens_per_candidate != null ? `${fmt(data.tokens_per_candidate)} per match` : `${fmt(data.output_tokens)} written`}
        />
      </dl>

      {(data.cache_read_tokens ?? 0) > 0 && (
        <p className="type-caption">{fmt(data.cache_read_tokens ?? 0)} input tokens came from the prompt cache.</p>
      )}

      {outcomes.length > 0 && (
        <Section title="Researched professors" meta={researched || undefined}>
          {(refusals?.lexical_scores ?? 0) > 0 && (
            <p className="rounded-md bg-muted/60 px-3 py-2 text-xs">
              {refusals?.lexical_scores} score{refusals?.lexical_scores === 1 ? " was" : "s were"} computed by matching
              shared words, because the embedding model was unavailable or rate-limited at the time. Related work
              worded differently can score low there.
            </p>
          )}
          <BarList rows={outcomes} unit="professors" />
        </Section>
      )}

      <ToolChart data={data} />

      <Breakdowns data={data} refusals={refusals?.refusals ?? []} />
    </div>
  )
}

/** Tool calls, succeeded and failed stacked, busiest first. */
function ToolChart({ data }: { data: Usage }) {
  const all = Object.entries(data.tools)
    .map(([name, s]) => ({ label: name.replaceAll("_", " "), ok: s.calls - s.errors, failed: s.errors, calls: s.calls }))
    .sort((a, b) => b.calls - a.calls)
  if (all.length === 0) return null
  const rest = all.slice(TOOL_ROWS)
  const rows = rest.length
    ? [
        ...all.slice(0, TOOL_ROWS),
        {
          label: `${rest.length} other tools`,
          ok: rest.reduce((n, r) => n + r.ok, 0),
          failed: rest.reduce((n, r) => n + r.failed, 0),
          calls: rest.reduce((n, r) => n + r.calls, 0),
        },
      ]
    : all
  const calls = all.reduce((n, r) => n + r.calls, 0)
  const failed = all.reduce((n, r) => n + r.failed, 0)
  return (
    <Section title="Tool calls" meta={calls}>
      <div className="flex gap-3 type-caption" aria-hidden>
        <Swatch color="var(--chart-1)" label="Succeeded" />
        <Swatch color="var(--chart-critical)" label={`Failed (${Math.round((failed / calls) * 100)}%)`} />
      </div>
      <ResponsiveContainer width="100%" height={rows.length * ROW_HEIGHT + 8}>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 36, bottom: 0, left: 0 }} barCategoryGap={4}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="label" width={LABEL_WIDTH} tick={<Tick />} tickLine={false} axisLine={false} interval={0} />
          <Tooltip {...TOOLTIP} />
          <Bar dataKey="ok" name="Succeeded" stackId="calls" fill="var(--chart-1)" maxBarSize={14} isAnimationActive={false} />
          <Bar dataKey="failed" name="Failed" stackId="calls" fill="var(--chart-critical)" radius={[0, 4, 4, 0]} maxBarSize={14} isAnimationActive={false} stroke="var(--background)" strokeWidth={1}>
            <LabelList dataKey="calls" position="right" style={TICK} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Section>
  )
}

/** Why professors took the full agent loop, and every check that refused a step. */
function Breakdowns({ data, refusals }: { data: Usage; refusals: { gate: string; label: string; count: number }[] }) {
  const paths = data.narrow_paths ?? {}
  const quick = (paths.no_match ?? 0) + (paths.likely ?? 0)
  const routed = quick + (paths.agent ?? 0)
  const fallbacks = Object.entries(data.narrow_fallbacks ?? {}).sort((a, b) => b[1] - a[1])
  const sections = [
    routed > 0 && {
      title: `${quick} of ${routed} professors took the quick path`,
      rows: fallbacks.map(([reason, count]) => ({ label: FALLBACK_LABELS[reason] ?? reason, count })),
    },
    refusals.length > 0 && {
      title: `${refusals.reduce((n, r) => n + r.count, 0).toLocaleString()} steps refused by a check`,
      rows: refusals.map((r) => ({ label: r.label, count: r.count })),
    },
  ].filter(Boolean) as { title: string; rows: { label: string; count: number }[] }[]
  if (sections.length === 0) return null
  return (
    <div className="divide-y divide-border border-y border-border">
      {sections.map((s) => (
        <details key={s.title} open className="group py-2 text-sm">
          <summary className="cursor-pointer type-caption hover:text-foreground">{s.title}</summary>
          <ul className="mt-2 space-y-1">
            {s.rows.map((r) => (
              <li key={r.label} className="flex justify-between gap-3">
                <span className="min-w-0 truncate">{r.label}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">{r.count.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  )
}

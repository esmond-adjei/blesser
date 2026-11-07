import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { TICK, TOOLTIP } from "./chartStyle"

/* Shared by run stats and account usage so the two read as one system. */

export function Stat({ label, value, detail, hint }: { label: string; value: string; detail: string; hint?: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border px-3 py-2" data-tooltip={hint}>
      <dt className="type-caption">{label}</dt>
      <dd className="truncate text-lg font-semibold tabular-nums">{value}</dd>
      <dd className="truncate type-caption" title={detail}>{detail}</dd>
    </div>
  )
}

export function Section({ title, meta, children }: { title: string; meta?: number; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-baseline gap-2 text-sm font-medium">
        {title}
        {meta != null && <span className="type-caption tabular-nums">{meta.toLocaleString()}</span>}
      </h3>
      {children}
    </section>
  )
}

export const ROW_HEIGHT = 26
export const LABEL_WIDTH = 150

/** Category label, cut to the axis width. */
export function Tick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const text = payload?.value ?? ""
  const shown = text.length > 24 ? `${text.slice(0, 23)}…` : text
  return (
    <text x={(x ?? 0) - 8} y={y} dy={4} textAnchor="end" {...TICK}>
      <title>{text}</title>
      {shown}
    </text>
  )
}

/** Rows with their own `fill` keep it; `format` writes the end labels and tooltip values. */
export function BarList({ rows, unit, format = (v) => v.toLocaleString() }: {
  rows: { label: string; value: number; fill: string }[]
  unit: string
  format?: (value: number) => string
}) {
  return (
    <ResponsiveContainer width="100%" height={rows.length * ROW_HEIGHT + 8}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 48, bottom: 0, left: 0 }} barCategoryGap={4}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="label" width={LABEL_WIDTH} tick={<Tick />} tickLine={false} axisLine={false} interval={0} />
        <Tooltip {...TOOLTIP} formatter={(v) => [`${format(Number(v))} ${unit}`, ""]} separator="" />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={14} isAnimationActive={false}>
          <LabelList dataKey="value" position="right" style={TICK} formatter={(v) => format(Number(v))} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-2.5 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  )
}


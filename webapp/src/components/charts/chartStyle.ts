/** Recharts styling shared by every chart, in theme tokens. */
export const TOOLTIP = {
  contentStyle: {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    fontSize: 12,
    color: "var(--foreground)",
  },
  labelStyle: { color: "var(--foreground)", fontWeight: 500 },
  itemStyle: { color: "var(--foreground)", padding: 0 },
  cursor: { fill: "var(--accent)" },
}

export const TICK = { fontSize: 12, fill: "var(--muted-foreground)" }

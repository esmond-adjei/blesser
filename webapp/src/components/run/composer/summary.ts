import { RUN_SIZES, sizeOf } from "../../../lib/runInference"
import { DEGREE_LABELS } from "../../../lib/vocab"
import { SCHOOL_TIERS } from "../runFormModel"
import type { SizeValue } from "./Pickers"

/** One-line summaries of the composer's choices, for the menu and its chip. */

export const shortDegree = (d: string) => (DEGREE_LABELS[d] ?? d).split(", ")[0]

export const tierLabel = (t: string) => SCHOOL_TIERS.find((x) => x.value === t)?.label ?? t

export function summarize(values: string[], empty: string, label: (v: string) => string = (v) => v): string {
  if (values.length === 0) return empty
  if (values.length === 1) return label(values[0])
  if (values.length === 2 && values.every((v) => label(v).length <= 8)) return values.map(label).join(" + ")
  return `${label(values[0])} +${values.length - 1}`
}

export function sizeLabel(value: SizeValue): string {
  const size = sizeOf(value)
  return size === "custom" ? `Custom, ${value.maxPrograms} schools` : RUN_SIZES[size].label
}

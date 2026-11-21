import * as React from "react"
import { Check, ChevronDown, Shapes } from "lucide-react"
import { cn } from "@blesser/ui"
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover"
import { KIND_LABELS } from "../../lib/opportunities"
import { MAX_SCAN_KINDS, SCAN_KINDS, kindsPhrase } from "../../lib/scanKinds"
import type { OpportunityKind } from "../../lib/types"

/** Picks up to three listing types for a scan, or none for any type. */
export function KindSelect({ value, onChange, side = "bottom" }: {
  value: OpportunityKind[]
  onChange: (kinds: OpportunityKind[]) => void
  side?: "top" | "bottom"
}) {
  const [open, setOpen] = React.useState(false)
  const full = value.length >= MAX_SCAN_KINDS
  const shown = value.length ? kindsPhrase(value) : "Any type"
  const toggle = (kind: OpportunityKind) =>
    onChange(value.includes(kind) ? value.filter((k) => k !== kind) : full ? value : [...value, kind])
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Looking for: ${shown}`}
          className="flex h-8 min-w-0 cursor-pointer items-center gap-1.5 rounded-full border border-separator px-3 text-footnote text-ink transition-colors hover:border-input-border-hover focus-visible:outline-2 focus-visible:outline-focus"
        >
          <Shapes className="size-3.5 shrink-0 text-ink-tertiary" aria-hidden="true" />
          <span className="max-w-40 truncate first-letter:uppercase">{shown}</span>
          <ChevronDown className="size-3.5 shrink-0 text-ink-tertiary" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent side={side} align="start" className="w-64 max-w-[calc(100vw-2rem)] p-1">
        <p className="px-2 pt-1.5 pb-1 text-caption text-ink-tertiary">Pick up to {MAX_SCAN_KINDS}, or none for any type</p>
        <ul role="listbox" aria-label="Listing types" aria-multiselectable="true" className="nice-scroll max-h-72 overflow-y-auto">
          {SCAN_KINDS.map((kind) => {
            const picked = value.includes(kind)
            const disabled = !picked && full
            return (
              <li key={kind} role="option" aria-selected={picked} aria-disabled={disabled}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => toggle(kind)}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-2.5 rounded-sm px-2 py-1.5 text-left text-callout transition-colors hover:bg-highlight focus-visible:bg-highlight focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50",
                    picked ? "text-ink" : "text-ink-secondary",
                  )}
                >
                  <span className="min-w-0 flex-1 truncate">{KIND_LABELS[kind]}</span>
                  {picked ? <Check className="size-4 shrink-0 text-link" aria-hidden="true" /> : null}
                </button>
              </li>
            )
          })}
        </ul>
        {value.length ? (
          <button type="button" onClick={() => onChange([])} className="mt-1 w-full cursor-pointer rounded-sm border-t border-separator px-2 py-1.5 text-left text-callout text-ink-secondary hover:bg-highlight hover:text-ink">
            Any type
          </button>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}

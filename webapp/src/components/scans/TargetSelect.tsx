import * as React from "react"
import { Check, ChevronDown, Shapes } from "lucide-react"
import { cn } from "@blesser/ui"
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover"
import { CATEGORIES, CATEGORY_LABELS, KIND_LABELS } from "../../lib/opportunities"
import { MAX_SCAN_KINDS, SCAN_KINDS, kindsPhrase } from "../../lib/scanKinds"
import type { OpportunityCategory, OpportunityKind } from "../../lib/types"

/** Who a scan is for and up to three listing types, in one control named like the scan. */
export function TargetSelect({ category, kinds, onCategory, onKinds, side = "bottom" }: {
  category: OpportunityCategory
  kinds: OpportunityKind[]
  onCategory: (category: OpportunityCategory) => void
  onKinds: (kinds: OpportunityKind[]) => void
  side?: "top" | "bottom"
}) {
  const [open, setOpen] = React.useState(false)
  const full = kinds.length >= MAX_SCAN_KINDS
  const shown = `${CATEGORY_LABELS[category]}, ${kinds.length ? kindsPhrase(kinds) : "any type"}`
  const toggle = (kind: OpportunityKind) =>
    onKinds(kinds.includes(kind) ? kinds.filter((k) => k !== kind) : full ? kinds : [...kinds, kind])
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Looking for: ${shown}`}
          className="flex h-8 min-w-0 cursor-pointer items-center gap-1.5 rounded-full border border-separator px-3 text-footnote font-medium text-ink transition-colors hover:border-input-border-hover focus-visible:outline-2 focus-visible:outline-focus"
        >
          <Shapes className="size-3.5 shrink-0 text-ink-tertiary" aria-hidden="true" />
          <span className="max-w-48 truncate">{shown}</span>
          <ChevronDown className="size-3.5 shrink-0 text-ink-tertiary" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent side={side} align="start" className="w-72 max-w-[calc(100vw-2rem)] p-1">
        <div role="radiogroup" aria-label="Audience" className="m-1 flex rounded-full bg-surface-sunk p-0.5">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={category === c}
              onClick={() => onCategory(c)}
              className={cn(
                "h-7 flex-1 cursor-pointer rounded-full px-2 text-footnote font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-focus",
                category === c ? "bg-surface text-ink shadow-elevation-1" : "text-ink-secondary hover:text-ink",
              )}
            >
              {CATEGORY_LABELS[c]}
            </button>
          ))}
        </div>
        <p className="px-2 pt-1.5 pb-1 text-caption text-ink-tertiary">Pick up to {MAX_SCAN_KINDS} types, or none for any</p>
        <ul role="listbox" aria-label="Listing types" aria-multiselectable="true" className="nice-scroll max-h-64 overflow-y-auto">
          {SCAN_KINDS.map((kind) => {
            const picked = kinds.includes(kind)
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
        {kinds.length ? (
          <button type="button" onClick={() => onKinds([])} className="mt-1 w-full cursor-pointer rounded-sm border-t border-separator px-2 py-1.5 text-left text-callout text-ink-secondary hover:bg-highlight hover:text-ink">
            Any type
          </button>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}

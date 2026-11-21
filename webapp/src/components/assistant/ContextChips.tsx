import { Briefcase, Award, Check, FolderOpen, ListChecks, TextQuote, X, type LucideIcon } from "lucide-react"
import { cn } from "@blesser/ui"
import { usePageContext } from "./pageContextState"

const ICONS: Record<string, LucideIcon> = {
  opportunity: Award,
  application: Briefcase,
  todo: ListChecks,
  project: FolderOpen,
  selection: TextQuote,
}

/** What the next question will carry about the open page; each chip can be turned off or dismissed. */
export function ContextChips() {
  const { chips, toggle, dismiss } = usePageContext()
  if (!chips.length) return null
  return (
    <div aria-label="Context for your question" className="nice-scroll mb-2 flex gap-1.5 overflow-x-auto">
      {chips.map((chip) => {
        const Icon = ICONS[chip.key] ?? Award
        const name = chip.detail ? `${chip.label}: ${chip.detail}` : chip.label
        return (
          <span
            key={chip.key}
            className={cn(
              "inline-flex min-w-0 max-w-full shrink-0 items-center rounded-full border text-caption",
              chip.added ? "border-forest/30 bg-forest-soft/40 text-ink" : "border-dashed border-input-border bg-surface text-ink-secondary",
            )}
          >
            <button
              type="button"
              onClick={() => toggle(chip.key)}
              aria-pressed={chip.added}
              title={chip.added ? `${name}. Included; click to leave it out` : `${name}. Click to include it`}
              className="inline-flex min-w-0 cursor-pointer items-center gap-1 rounded-l-full py-1 pr-1 pl-2.5 hover:text-ink focus-visible:outline-2 focus-visible:outline-focus"
            >
              {chip.added ? <Check className="size-3 shrink-0" aria-hidden="true" /> : <Icon className="size-3 shrink-0" aria-hidden="true" />}
              <span className="max-w-44 truncate">{chip.detail ?? chip.label}</span>
            </button>
            <button
              type="button"
              onClick={() => dismiss(chip.key)}
              aria-label={`Remove ${chip.label}`}
              className="cursor-pointer rounded-r-full py-1 pr-2 pl-0.5 hover:text-ink focus-visible:outline-2 focus-visible:outline-focus"
            >
              <X className="size-3" aria-hidden="true" />
            </button>
          </span>
        )
      })}
    </div>
  )
}

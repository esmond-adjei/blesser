import * as React from "react"
import { Check, ChevronDown, Search, Settings, Sparkles } from "lucide-react"
import { useLocation, useNavigate } from "react-router-dom"
import { useProviderCatalog, useProviderConfigs, usableConfigs } from "../../lib/providers"
import { cn } from "../../lib/utils"
import { ProviderIcon } from "./ProviderIcon"
import { useKeepInViewport } from "./keepInViewport"
import { useDismiss } from "../../lib/useDismiss"

const ROW = "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-accent"

interface Choice {
  value: string
  label: string
  detail: string
  /** Strings the search box matches against. */
  search: string[]
  /** Show a check column instead of a highlighted row when selected. */
  check?: boolean
  badge?: string
  provider?: string
}

function ChoiceRow({ choice, selected, onPick }: { choice: Choice; selected: boolean; onPick: () => void }) {
  const { label, detail, check, badge, provider } = choice
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={selected}
      onClick={onPick}
      className={cn(ROW, !check && selected && "bg-tint-soft")}
    >
      {check && <span className="w-4 shrink-0 text-center">{selected && <Check className="size-3.5" />}</span>}
      {provider && <ProviderIcon provider={provider} className="size-4 shrink-0" />}
      <span className="min-w-0 flex-1">
        <span className="block truncate">
          {label}
          {badge && (
            <span className="ml-1.5 rounded bg-primary/10 px-1 py-px font-sans text-xs text-primary">{badge}</span>
          )}
        </span>
        <span className="block truncate type-caption">{detail}</span>
      </span>
    </button>
  )
}

/** Values are "auto"/"system", an enabled own model, or one of `extras`. */
export function ModelDropup({
  value,
  onChange,
  placement = "up",
  extras = [],
}: {
  value: string
  onChange: (sel: string) => void
  /** "up" opens above the pill (chat), "down" below it (composer). */
  placement?: "up" | "down"
  /** Choices listed above Auto (a run's "Default", say). */
  extras?: { value: string; label: string; detail: string }[]
}) {
  const { configs } = useProviderConfigs()
  const { providers, system } = useProviderCatalog()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")
  const boxRef = React.useRef<HTMLSpanElement>(null)
  const inputRef = React.useRef<HTMLInputElement>(null)
  const menuRef = React.useRef<HTMLDivElement>(null)
  useKeepInViewport(menuRef, open)

  React.useEffect(() => {
    if (!open) return
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])
  useDismiss(open, boxRef, () => setOpen(false))

  const autoDetail = system?.model ? `${system.provider}, ${system.model}` : "No model configured"

  // Every selectable row, in display order. Switched-off models aren't
  // offered; they keep their settings. Auto is the system model, not a user row.
  const choices: Choice[] = [
    ...extras.map((e) => ({ ...e, search: [e.label, e.detail], check: true })),
    { value: "auto", label: "Auto", detail: autoDetail, search: ["auto", "system", autoDetail], provider: system?.provider },
    ...usableConfigs(configs).map((m) => ({
      value: m.provider,
      label: m.model,
      detail: m.provider,
      search: [m.model, m.provider],
      badge: m.is_active ? "default" : undefined,
      provider: m.provider,
    })),
  ]

  const requested = value === "system" ? "auto" : value
  const current = choices.some((c) => c.value === requested) ? requested : (extras[0]?.value ?? "auto")
  const active = choices.find((c) => c.value === current)

  const configured = new Set(configs.filter((c) => c.model).map((c) => c.provider))
  const q = query.trim().toLowerCase()
  const matches = (...texts: string[]) => !q || texts.some((t) => t.toLowerCase().includes(q))
  const visibleChoices = choices.filter((c) => matches(...c.search))
  const pending = providers.filter((p) => !configured.has(p.provider) && matches(p.provider))

  const close = () => setOpen(false)

  function pick(sel: string) {
    onChange(sel)
    close()
  }

  function manage() {
    close()
    const params = new URLSearchParams(location.search)
    params.set("settings", "models")
    navigate(`${location.pathname}?${params.toString()}`)
  }

  return (
    <span ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => {
          if (!open) setQuery("")
          setOpen((o) => !o)
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        data-tooltip={`Model: ${active?.label}${active ? ` (${active.detail})` : ""}`}
        aria-label={`Model: ${active?.label}`}
        className="flex h-7 cursor-pointer items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground @max-[24rem]/composer:w-7 @max-[24rem]/composer:justify-center @max-[24rem]/composer:px-0"
      >
        {active?.provider ? <ProviderIcon provider={active.provider} className="size-3.5 shrink-0" /> : <Sparkles className="size-3.5 shrink-0" />}
        <span className="max-w-24 truncate @max-[24rem]/composer:hidden">{active?.label}</span>
        <ChevronDown className={cn("size-3 transition-transform @max-[24rem]/composer:hidden", open && "rotate-180")} />
      </button>
      {open && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="Choose a model"
          className={cn(
            "absolute z-20 w-64 text-sm depth-fade max-w-[calc(100vw-1rem)] overflow-hidden rounded-xl border border-border bg-popover shadow-xl",
            placement === "up" ? "bottom-full left-0 mb-2" : "right-0 top-full mt-2",
          )}
        >
          <div className="p-2 pb-1">
            <div className="flex items-center gap-1.5 rounded-md border border-ring bg-background px-2 py-1.5">
              <Search className="size-3.5 shrink-0 text-muted-foreground" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search models"
                aria-label="Search models"
                spellCheck={false}
                className="w-full bg-transparent outline-none placeholder:text-muted-foreground"
              />
            </div>
          </div>
          <div className="nice-scroll max-h-72 space-y-1 overflow-y-auto p-1">
            {visibleChoices.map((c) => (
              <ChoiceRow key={c.value} choice={c} selected={c.value === current} onPick={() => pick(c.value)} />
            ))}
            {pending.map((p) => (
              <button
                key={p.provider}
                type="button"
                role="menuitem"
                onClick={manage}
                data-tooltip={`Configure ${p.provider} in settings`}
                className={cn(ROW, "group")}
              >
                <ProviderIcon provider={p.provider} className="size-4 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{p.provider}</span>
                <Settings className="group-hover:text-tint size-3.5 shrink-0 text-muted-foreground" />
              </button>
            ))}
            {!visibleChoices.length && !pending.length && (
              <p className="px-2 py-3 text-center type-caption">No models match.</p>
            )}
          </div>
          <div className="border-t border-border p-1">
            <button type="button" role="menuitem" onClick={manage} className={cn(ROW, "text-sm")}>
              <span className="w-4 shrink-0" />
              <span className="flex-1">Manage Models...</span>
            </button>
          </div>
        </div>
      )}
    </span>
  )
}

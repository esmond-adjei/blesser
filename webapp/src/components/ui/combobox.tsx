import * as React from "react"
import { Check, ChevronsUpDown } from "lucide-react"
import { cn } from "../../lib/utils"

export interface ComboboxOption {
  value: string
  label: string
  hint?: string
  badge?: string
}

type SingleProps = {
  multiple?: false
  value: string | null
  onChange: (value: string) => void
}

type MultiProps = {
  multiple: true
  values: string[]
  onToggle: (value: string) => void
}

type ComboboxProps = {
  options: ComboboxOption[]
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  /** Show a "Use ..." row that commits the raw query (custom entries). */
  allowCustom?: boolean
  customLabel?: (query: string) => string
  onCustom?: (query: string) => void
  disabled?: boolean
  className?: string
  /** Forwarded to the trigger so a FormField label/error can attach. */
  id?: string
  "aria-invalid"?: boolean
  "aria-describedby"?: string
} & (SingleProps | MultiProps)

/** Dependency-free searchable combobox; single mode closes on select, multi stays open. */
export function Combobox(props: ComboboxProps) {
  const {
    options,
    placeholder = "Select...",
    searchPlaceholder = "Search...",
    emptyText = "Nothing found.",
    allowCustom = false,
    customLabel = (q) => `Use "${q}"`,
    disabled = false,
    className,
  } = props
  const multiple = props.multiple === true

  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")
  const [active, setActive] = React.useState(0)
  const rootRef = React.useRef<HTMLDivElement>(null)
  const searchRef = React.useRef<HTMLInputElement>(null)
  const listRef = React.useRef<HTMLDivElement>(null)

  const selectedValues: string[] = multiple ? props.values : props.value ? [props.value] : []
  const selectedSet = new Set(selectedValues)
  const byValue = React.useMemo(() => new Map(options.map((o) => [o.value, o])), [options])

  const q = query.trim().toLowerCase()
  const visible = q
    ? options.filter((o) => `${o.label} ${o.hint ?? ""}`.toLowerCase().includes(q))
    : options
  const showCustom = allowCustom && q.length > 0 && !visible.some((o) => o.label.toLowerCase() === q)
  const rowCount = visible.length + (showCustom ? 1 : 0)

  React.useEffect(() => {
    if (open) {
      setQuery("")
      setActive(0)
      searchRef.current?.focus()
    }
  }, [open ])

  React.useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("pointerdown", onDown)
    return () => document.removeEventListener("pointerdown", onDown)
  }, [open ])

  React.useEffect(() => {
    listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "nearest" })
  }, [active, open])

  function commitCustom() {
    const trimmed = query.trim()
    if (!trimmed) return
    if (!multiple) (props as SingleProps).onChange(trimmed)
    props.onCustom?.(trimmed)
    setOpen(false)
  }

  function commitOption(value: string) {
    if (multiple) (props as MultiProps).onToggle(value)
    else {
      (props as SingleProps).onChange(value)
      setOpen(false)
    }
  }

  function onSearchKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setActive((i) => (rowCount > 0 ? (i + 1) % rowCount : 0))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActive((i) => (rowCount > 0 ? (i - 1 + rowCount) % rowCount : 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      if (showCustom && active === visible.length) commitCustom()
      else {
        const opt = visible[active]
        if (opt) commitOption(opt.value)
      }
    } else if (e.key === "Escape") {
      e.preventDefault()
      setOpen(false)
    }
  }

  const triggerLabel = multiple
    ? selectedValues.length === 0
      ? placeholder
      : selectedValues.length === 1
        ? (byValue.get(selectedValues[0])?.label ?? selectedValues[0])
        : `${selectedValues.length} selected`
    : (props as SingleProps).value
      ? (byValue.get((props as SingleProps).value as string)?.label ?? (props as SingleProps).value)
      : placeholder
  const hasSelection = selectedValues.length > 0

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        id={props.id}
        aria-invalid={props["aria-invalid"]}
        aria-describedby={props["aria-describedby"]}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={cn(
          "flex h-9 w-full cursor-pointer items-center gap-2 rounded-md border border-input bg-background px-3 py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive",
          !hasSelection && "text-muted-foreground",
        )}
      >
        <span className="min-w-0 flex-1 truncate text-left">{triggerLabel}</span>
        <ChevronsUpDown className="size-4 shrink-0 opacity-50" />
      </button>

      {open && (
        <div className="absolute inset-x-0 top-full z-50 mt-1 overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-xl">
          <div className="border-b border-border p-1.5">
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setActive(0)
              }}
              onKeyDown={onSearchKey}
              placeholder={searchPlaceholder}
              aria-label="Filter options"
              className="h-8 w-full rounded-sm bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div ref={listRef} role="listbox" className="nice-scroll max-h-56 overflow-y-auto p-1">
            {visible.map((o, i) => {
              const selected = selectedSet.has(o.value)
              return (
                <button
                  key={o.value}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  data-active={i === active || undefined}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => commitOption(o.value)}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm transition-colors",
                    i === active && "bg-accent text-accent-foreground",
                  )}
                >
                  {multiple && (
                    <span
                      className={cn(
                        "flex size-4 shrink-0 items-center justify-center rounded-sm border",
                        selected ? "border-primary bg-primary text-primary-foreground" : "border-input",
                      )}
                    >
                      {selected && <Check className="size-3" />}
                    </span>
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{o.label}</span>
                    {o.hint && <span className="block truncate type-caption">{o.hint}</span>}
                  </span>
                  {o.badge && (
                    <span className="shrink-0 rounded-xs bg-fill-quiet px-1.5 py-0.5 text-xs font-medium text-label-secondary">
                      {o.badge}
                    </span>
                  )}
                  {!multiple && selected && <Check className="size-4 shrink-0" />}
                </button>
              )
            })}
            {showCustom && (
              <button
                type="button"
                data-active={active === visible.length || undefined}
                onMouseEnter={() => setActive(visible.length)}
                onClick={commitCustom}
                className={cn(
                  "flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm transition-colors",
                  active === visible.length && "bg-accent text-accent-foreground",
                )}
              >
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {customLabel(query.trim())}
                </span>
              </button>
            )}
            {rowCount === 0 && (
              <p className="px-2 py-4 text-center type-meta">{emptyText}</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

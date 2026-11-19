import * as React from "react"
import { Check, ChevronDown, Globe, Search } from "lucide-react"
import { cn } from "@blesser/ui"
import { Popover, PopoverContent, PopoverTrigger } from "./popover"

// Each flag is its own asset, fetched only when shown.
const FLAG_URLS = import.meta.glob("../../../../node_modules/country-flag-icons/3x2/*.svg", {
  query: "?url",
  import: "default",
  eager: true,
}) as Record<string, string>

const names = new Intl.DisplayNames(["en"], { type: "region" })

export const COUNTRIES: { code: string; name: string; flag: string }[] = Object.entries(FLAG_URLS)
  .map(([path, flag]) => {
    const code = path.slice(path.lastIndexOf("/") + 1, -4)
    let name = code
    try {
      name = names.of(code) ?? code
    } catch {
      // Sub-national codes like GB-SCT have no display name.
    }
    return { code, name, flag }
  })
  .filter((c) => c.code.length === 2 && c.name !== c.code)
  .sort((a, b) => a.name.localeCompare(b.name))

const byName = new Map(COUNTRIES.map((c) => [c.name.toLowerCase(), c]))

export function Flag({ code, className }: { code: string; className?: string }) {
  const country = COUNTRIES.find((c) => c.code === code)
  if (!country) return null
  return <img src={country.flag} alt="" loading="lazy" className={cn("h-3 w-[18px] shrink-0 rounded-[2px] object-cover ring-1 ring-separator", className)} />
}

/** Picks one country by name, or Anywhere (an empty value). */
export function CountrySelect({ value, onChange, label = "Where", className, side = "bottom" }: {
  value: string
  onChange: (name: string) => void
  label?: string
  className?: string
  side?: "top" | "bottom"
}) {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")
  const [active, setActive] = React.useState(0)
  const listRef = React.useRef<HTMLUListElement>(null)
  const listId = React.useId()
  const selected = byName.get(value.trim().toLowerCase())
  const q = query.trim().toLowerCase()
  const options = [
    ...(!q || "anywhere".includes(q) ? [{ code: "", name: "Anywhere", flag: "" }] : []),
    ...COUNTRIES.filter((c) => !q || c.name.toLowerCase().includes(q) || c.code.toLowerCase() === q),
  ]
  const current = Math.min(active, Math.max(options.length - 1, 0))

  React.useEffect(() => {
    listRef.current?.querySelector(`[data-index="${current}"]`)?.scrollIntoView({ block: "nearest" })
  }, [current])

  const pick = (name: string) => {
    onChange(name === "Anywhere" ? "" : name)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={(o) => {
      setOpen(o)
      if (o) {
        setQuery("")
        setActive(Math.max(0, options.findIndex((c) => c.name === (selected?.name ?? "Anywhere"))))
      }
    }}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`${label}: ${selected?.name ?? (value || "Anywhere")}`}
          className={cn(
            "flex h-8 min-w-0 cursor-pointer items-center gap-1.5 rounded-full border border-separator px-3 text-footnote text-ink transition-colors hover:border-input-border-hover focus-visible:outline-2 focus-visible:outline-focus",
            className,
          )}
        >
          {selected ? <Flag code={selected.code} /> : <Globe className="size-3.5 shrink-0 text-ink-tertiary" aria-hidden="true" />}
          <span className="max-w-32 truncate">{selected?.name ?? (value || "Anywhere")}</span>
          <ChevronDown className="size-3.5 shrink-0 text-ink-tertiary" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent side={side} align="start" className="w-72 max-w-[calc(100vw-2rem)] overflow-hidden p-0">
        <div className="flex items-center gap-2 border-b border-separator px-3">
          <Search className="size-4 shrink-0 text-ink-tertiary" aria-hidden="true" />
          <input
            autoFocus
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={options[current] ? `${listId}-${current}` : undefined}
            aria-label="Search countries"
            placeholder="Search countries"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0) }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, options.length - 1)) }
              else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)) }
              else if (e.key === "Enter") { e.preventDefault(); if (options[current]) pick(options[current].name) }
            }}
            className="h-10 min-w-0 flex-1 bg-transparent text-callout text-ink outline-none placeholder:text-ink-tertiary"
          />
        </div>
        <ul ref={listRef} id={listId} role="listbox" aria-label="Countries" className="nice-scroll max-h-64 overflow-y-auto p-1">
          {options.map((c, i) => {
            const isSelected = c.code ? selected?.code === c.code : !selected && !value
            return (
              <li
                key={c.code || "anywhere"}
                id={`${listId}-${i}`}
                data-index={i}
                role="option"
                aria-selected={isSelected}
                onMouseMove={() => setActive(i)}
                onClick={() => pick(c.name)}
                className={cn("flex cursor-pointer items-center gap-2.5 rounded-sm px-2 py-1.5 text-callout", i === current ? "bg-highlight text-ink" : "text-ink-secondary")}
              >
                {c.code ? <Flag code={c.code} /> : <Globe className="size-3.5 w-[18px] text-ink-tertiary" aria-hidden="true" />}
                <span className="min-w-0 flex-1 truncate">{c.name}</span>
                {isSelected ? <Check className="size-4 shrink-0 text-link" aria-hidden="true" /> : null}
              </li>
            )
          })}
          {!options.length ? <li className="px-2 py-6 text-center text-callout text-ink-secondary">No country matches "{query.trim()}".</li> : null}
        </ul>
      </PopoverContent>
    </Popover>
  )
}

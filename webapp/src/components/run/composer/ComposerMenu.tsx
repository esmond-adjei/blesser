import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, GitBranch, GraduationCap, Landmark, Layers, MapPin, Plus, Settings2, SlidersHorizontal, Sparkles, Tag } from "lucide-react"
import { Link } from "react-router-dom"
import * as api from "../../../lib/api"
import { useCvDocuments } from "../../../lib/queries"
import { inferFromInterest, type Inferred } from "../../../lib/runInference"
import type { ProgramSeed, SchoolTier } from "../../../lib/types"
import { cn } from "../../../lib/utils"
import { ANYWHERE } from "../../../lib/vocab"
import { Popover } from "../../ui/popover"
import { DegreeOptions, FieldOptions, FlowOptions, PlaceOptions, SchoolsOptions, SizeOptions, TierOptions, type SizeValue } from "./Pickers"
import { shortDegree, sizeLabel, summarize, tierLabel } from "./summary"

export interface MenuValue extends SizeValue {
  interest: string
  degrees: string[]
  regions: string[]
  fields: string[]
  schoolTiers: SchoolTier[]
  seeds: ProgramSeed[]
}

type Section = "degree" | "where" | "field" | "tiers" | "size" | "flow"

interface Item {
  key: Section
  icon: React.ReactNode
  label: string
  current?: string
  description: string
  /** Hidden because specific schools skip discovery. */
  skipped?: boolean
}

/** One menu for every option, so the composer's controls stay on one line at any width. */
export function ComposerMenu<V extends MenuValue>({
  value,
  onChange,
  auto,
  onAutoChange,
  inferred,
  recentPlaces,
  anchor,
}: {
  value: V
  onChange: (v: V) => void
  auto: { degrees: boolean; regions: boolean; fields: boolean }
  onAutoChange: (a: { degrees: boolean; regions: boolean; fields: boolean }) => void
  inferred: Inferred
  recentPlaces: string[]
  /** The composer card: the menu opens under it, at its width. */
  anchor: React.RefObject<HTMLElement | null>
}) {
  const [section, setSection] = React.useState<Section>("degree")
  // Phones: the list first, then one item's options with a way back.
  const [paneOnly, setPaneOnly] = React.useState(false)
  const narrow = useNarrow()
  const { data: flows } = useQuery({ queryKey: ["flows"], queryFn: api.listFlows, staleTime: 30_000 })
  const set = <K extends keyof V>(k: K, v: V[K]) => onChange({ ...value, [k]: v })
  const seeded = value.seeds.length > 0
  const fields = auto.fields ? inferred.fields : value.fields
  const flowList = flows?.flows ?? []

  const items: Item[] = [
    { key: "degree", icon: <GraduationCap />, label: "Degree", current: summarize(value.degrees, "Any degree", shortDegree), description: "The degrees to look for programmes in." },
    { key: "where", icon: <MapPin />, label: "Where", current: summarize(value.regions, ANYWHERE), description: "Countries or regions to search.", skipped: seeded },
    {
      key: "field",
      icon: <Tag />,
      label: "Field",
      current: auto.fields ? `${fields[0] ?? "Read from your interest"}, auto` : summarize(value.fields, "Any field"),
      description: "The field programmes are in. Auto reads it from what you typed.",
      skipped: seeded,
    },
    { key: "tiers", icon: <Layers />, label: "School tiers", current: summarize(value.schoolTiers, "Any tier", tierLabel), description: "How selective the schools should be.", skipped: seeded },
    { key: "size", icon: <Settings2 />, label: "Run size", current: sizeLabel(value), description: "How many schools to search and professors to keep." },
    ...(flowList.length > 1 || value.flowId !== "standard"
      ? [{ key: "flow" as const, icon: <GitBranch />, label: "Flow", current: flowList.find((f) => f.id === value.flowId)?.name ?? "Standard research", description: "How the run works, step by step." }]
      : []),
  ]
  const active = items.find((i) => i.key === section) ?? items[0]

  function pick(s: Section) {
    setSection(s)
    if (narrow) setPaneOnly(true)
  }

  const summary = summaryText(value, auto, fields)
  return (
    <Popover
      label="Run options"
      anchor={anchor}
      onOpenChange={(o) => {
        if (!o) setPaneOnly(false)
      }}
      className="sm:p-0"
      trigger={(p) => (
        <button
          {...p}
          type="button"
          data-tooltip="Change run options"
          aria-label={`Run options: ${summary}`}
          className="flex h-7 min-w-0 cursor-pointer items-center gap-1.5 rounded-full px-2 border border-border hover:border-foreground/20 type-caption hover:bg-accent hover:text-foreground aria-expanded:bg-accent aria-expanded:text-foreground"
        >
          <SlidersHorizontal className="size-3.5 shrink-0" />
          <span className="truncate">{summary}</span>
        </button>
      )}
    >
      {() => (
        <div className="flex min-h-0 sm:h-88">
          {(!narrow || !paneOnly) && (
            <nav
              aria-label="Run options"
              className="nice-scroll w-full shrink-0 overflow-y-auto space-y-1 sm:w-56 sm:border-r sm:border-border sm:p-1.5"
              onKeyDown={(e) => {
                if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return
                e.preventDefault()
                e.stopPropagation()
                const all = items.filter((i) => !i.skipped)
                const at = all.findIndex((i) => i.key === section)
                const next = all[(at + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length]
                setSection(next.key)
                document.getElementById(`composer-menu-${next.key}`)?.focus()
              }}
            >
              {items.map((i) => (
                <NavItem key={i.key} item={i} selected={!narrow && i.key === section} onSelect={() => pick(i.key)} onFocus={() => setSection(i.key)} />
              ))}
            </nav>
          )}
          {(!narrow || paneOnly) && (
            <section aria-label={active.label} className="nice-scroll min-w-0 flex-1 overflow-y-auto sm:p-3">
              {narrow && (
                <button
                  type="button"
                  onClick={() => setPaneOnly(false)}
                  className="mb-2 flex cursor-pointer items-center gap-1 type-caption hover:text-foreground"
                >
                  <ArrowLeft className="size-3.5" /> All options
                </button>
              )}
              <div className="mb-2 px-1">
                <p className="flex items-center gap-2 text-sm font-semibold [&_svg]:size-4">
                  {active.icon}
                  {active.label}
                </p>
                <p className="mt-0.5 type-caption">{active.description}</p>
              </div>
              {active.skipped ? (
                <p className="px-1 type-meta">
                  You added specific schools, so discovery is skipped and this doesn't apply.
                </p>
              ) : active.key === "degree" ? (
                <DegreeOptions
                  value={value.degrees}
                  onChange={(d) => {
                    onAutoChange({ ...auto, degrees: false })
                    set("degrees", d)
                  }}
                />
              ) : active.key === "where" ? (
                <PlaceOptions
                  value={value.regions}
                  recent={recentPlaces}
                  onChange={(r) => {
                    onAutoChange({ ...auto, regions: false })
                    set("regions", r)
                  }}
                />
              ) : active.key === "field" ? (
                <FieldOptions
                  value={value.fields}
                  auto={auto.fields}
                  inferred={inferred.fields}
                  onChange={(f) => {
                    onAutoChange({ ...auto, fields: false })
                    set("fields", f)
                  }}
                  onAuto={() => {
                    onAutoChange({ ...auto, fields: true })
                    set("fields", [])
                  }}
                />
              ) : active.key === "tiers" ? (
                <TierOptions value={value.schoolTiers} onChange={(t) => set("schoolTiers", t)} />
              ) : active.key === "size" ? (
                <SizeOptions value={value} onChange={(s) => onChange({ ...value, ...s })} />
              ) : (
                <FlowOptions value={value.flowId} onChange={(id) => set("flowId", id)} />
              )}
            </section>
          )}
        </div>
      )}
    </Popover>
  )
}

/** "+": attach specific schools; listed schools skip discovery. */
export function SchoolsMenu({ value, onAdd, anchor }: {
  value: MenuValue
  onAdd: (seeds: ProgramSeed[]) => void
  anchor: React.RefObject<HTMLElement | null>
}) {
  const fallbackProgram = value.fields[0] ?? inferFromInterest(value.interest).fields[0] ?? "Graduate programme"
  return (
    <Popover
      label="Specific schools"
      anchor={anchor}
      className="sm:p-3"
      trigger={(p) => (
        <button
          {...p}
          type="button"
          data-tooltip="Add specific schools"
          aria-label="Add specific schools"
          className="flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-full border border-border text-muted-foreground hover:border-foreground/20 hover:text-foreground aria-expanded:border-ring"
        >
          <Plus className="size-4" />
        </button>
      )}
    >
      {(close) => (
        <div>
          <div className="mb-2 px-1">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <Landmark className="size-4" /> Specific schools
            </p>
            <p className="mt-0.5 type-caption">
              One per line: School — Programme. Department URLs work too. These skip discovery.
            </p>
          </div>
          <SchoolsOptions
            fallbackProgram={fallbackProgram}
            onAdd={(seeds) => {
              onAdd(seeds)
              close()
            }}
          />
        </div>
      )}
    </Popover>
  )
}

/** With more than one CV it asks which to read first; with none it points to the CV page. */
export function CvSuggestButton({ onSuggest }: { onSuggest?: (documentId: string) => void }) {
  const docs = useCvDocuments()
  // Interests come from CVs, not the other kinds of document.
  const list = (docs.data ?? []).filter((d) => (d.kind ?? "cv") === "cv")
  const cls =
    "flex h-7 shrink-0 cursor-pointer items-center gap-1.5 rounded-full border border-border px-2.5 text-xs text-muted-foreground hover:border-foreground/20 hover:text-foreground"
  const face = (
    <>
      <Sparkles className="size-3.5" />
      <span className="hidden sm:inline">Add from CV</span>
    </>
  )
  if (list.length === 0 || !onSuggest) {
    return (
      <Link to="/documents" data-tooltip="Add your CV to get interest suggestions" className={cls}>
        {face}
      </Link>
    )
  }
  if (list.length === 1) {
    return (
      <button
        type="button"
        onClick={() => onSuggest(list[0].id)}
        data-tooltip={`Suggest interests from ${list[0].title}`}
        aria-label="Suggest interests from my CV"
        className={cls}
      >
        {face}
      </button>
    )
  }
  return (
    <Popover
      label="Choose a CV"
      className="sm:w-72"
      trigger={(props) => (
        <button type="button" {...props} data-tooltip="Suggest interests from a CV" aria-label="Suggest interests from a CV" className={cls}>
          {face}
        </button>
      )}
    >
      {(close) => (
        <div className="p-1.5">
          <p className="px-2 pb-1.5 pt-1 text-xs text-muted-foreground">Suggest interests from</p>
          <ul aria-label="Your CVs">
            {list.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => {
                    close()
                    onSuggest(d.id)
                  }}
                  className="flex w-full cursor-pointer flex-col items-start rounded-md px-2 py-1.5 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
                >
                  <span className="w-full truncate text-sm font-medium">{d.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {d.format.toUpperCase()}
                    {d.version_count > 0 && `, ${d.version_count} tailored version${d.version_count === 1 ? "" : "s"}`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Popover>
  )
}

/** What the run will do, in a line: "PhD, Canada, Robotics (auto)". */
function summaryText(value: MenuValue, auto: { fields: boolean }, fields: string[]): string {
  const parts = [summarize(value.degrees, "Any degree", shortDegree)]
  if (value.seeds.length > 0) {
    parts.push(`${value.seeds.length} school${value.seeds.length === 1 ? "" : "s"}`)
  } else {
    parts.push(summarize(value.regions, ANYWHERE))
    if (auto.fields) {
      if (fields[0]) parts.push(`${fields[0]} (auto)`)
    } else if (value.fields.length) {
      parts.push(summarize(value.fields, ""))
    }
    if (value.schoolTiers.length) parts.push(summarize(value.schoolTiers, "", tierLabel))
  }
  const size = sizeLabel(value)
  if (size !== "Standard") parts.push(size)
  return parts.join(", ")
}

function NavItem({ item, selected, onSelect, onFocus }: { item: Item; selected: boolean; onSelect: () => void; onFocus: () => void }) {
  return (
    <button
      id={`composer-menu-${item.key}`}
      type="button"
      onClick={onSelect}
      onFocus={onFocus}
      aria-current={selected ? "true" : undefined}
      disabled={item.skipped}
      className={cn(
        "flex w-full cursor-pointer items-start gap-2.5 rounded-md px-2.5 py-2 text-left text-sm hover:bg-accent disabled:cursor-default disabled:opacity-50 disabled:hover:bg-transparent [&_svg]:mt-0.5 [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground",
        selected && "bg-accent",
      )}
    >
      {item.icon}
      <span className="min-w-0 flex-1">
        <span className="block">{item.label}</span>
        {item.current && <span className="block truncate type-caption">{item.skipped ? "Skipped" : item.current}</span>}
      </span>
    </button>
  )
}

function useNarrow(): boolean {
  const query = "(max-width: 639px)"
  const [narrow, setNarrow] = React.useState(() => typeof window !== "undefined" && !!window.matchMedia?.(query).matches)
  React.useEffect(() => {
    const mq = window.matchMedia?.(query)
    if (!mq) return
    const on = () => setNarrow(mq.matches)
    mq.addEventListener("change", on)
    return () => mq.removeEventListener("change", on)
  }, [])
  return narrow
}

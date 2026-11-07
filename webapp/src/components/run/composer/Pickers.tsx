import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { Landmark, Minus, Plus } from "lucide-react"
import { Link } from "react-router-dom"
import * as api from "../../../lib/api"
import { RUN_SIZES, parseSchoolLines, sizeOf, type RunSize } from "../../../lib/runInference"
import type { ProgramSeed, SchoolTier } from "../../../lib/types"
import { cn } from "../../../lib/utils"
import {
  ANYWHERE,
  DEGREE_LABELS,
  DEGREE_VOCAB,
  FIELD_VOCAB,
  PLACE_VOCAB,
  canonical,
  searchVocab,
  type VocabEntry,
} from "../../../lib/vocab"
import { Button } from "../../ui/button"
import { PopoverOption } from "../../ui/popover"
import { RUN_DIALS, SCHOOL_TIERS } from "../runFormModel"

/* Option panels for the composer menu; one-line summaries live in ./summary. */

/** Search box at the top of a panel. Enter takes the first match. */
function FilterInput({ value, onChange, placeholder, onEnter }: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  onEnter: () => void
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault()
          onEnter()
        }
      }}
      placeholder={placeholder}
      aria-label={placeholder}
      className="mb-1 h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
    />
  )
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return <p className="px-2.5 pb-0.5 pt-2 type-group-label font-medium">{children}</p>
}

export function DegreeOptions({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [q, setQ] = React.useState("")
  const matches = searchVocab(q, DEGREE_VOCAB, 12)
  const custom = q.trim() && !matches.some((m) => m.aliases.includes(q.trim().toLowerCase())) ? q.trim() : null
  const toggle = (d: string) => onChange(value.includes(d) ? value.filter((x) => x !== d) : [...value, d])
  return (
    <div>
      <FilterInput
        value={q}
        onChange={setQ}
        placeholder="Find or add a degree"
        onEnter={() => {
          if (matches[0]) toggle(matches[0].value)
          else if (custom) toggle(custom)
          setQ("")
        }}
      />
      {matches.map((m) => (
        <PopoverOption key={m.value} selected={value.includes(m.value)} onSelect={() => toggle(m.value)}>
          {DEGREE_LABELS[m.value] ?? m.value}
        </PopoverOption>
      ))}
      {value
        .filter((v) => !DEGREE_LABELS[v])
        .map((v) => (
          <PopoverOption key={v} selected onSelect={() => toggle(v)}>
            {v}
          </PopoverOption>
        ))}
      {custom && (
        <PopoverOption selected={false} onSelect={() => { toggle(custom); setQ("") }}>
          Other: “{custom}”
        </PopoverOption>
      )}
    </div>
  )
}

function TypeaheadOptions({
  vocab,
  value,
  onChange,
  lead,
  recent = [],
  placeholder,
}: {
  vocab: VocabEntry[]
  value: string[]
  onChange: (v: string[]) => void
  /** The exclusive first option (Anywhere / Auto), selected while value is empty. */
  lead: { label: string; hint?: string; selected: boolean; onSelect: () => void }
  recent?: string[]
  placeholder: string
}) {
  const [q, setQ] = React.useState("")
  const matches = searchVocab(q, vocab, q ? 8 : 0)
  const typed = q.trim()
  // Offer "Add" only when nothing listed starts with what was typed: "can"
  // means Canada, not a custom place called "can".
  const lowered = typed.toLowerCase()
  const custom =
    typed && canonical(typed, vocab) === typed && !matches.some((m) => m.aliases.some((a) => a.startsWith(lowered)))
      ? typed
      : null
  const add = (v: string) => {
    if (!value.includes(v)) onChange([...value, v])
    setQ("")
  }
  const toggle = (v: string) => (value.includes(v) ? onChange(value.filter((x) => x !== v)) : add(v))
  const groups = new Map<string, VocabEntry[]>()
  for (const m of matches) groups.set(m.group ?? "", [...(groups.get(m.group ?? "") ?? []), m])
  const recentShown = q ? [] : recent.filter((r) => !value.includes(r))
  return (
    <div>
      <FilterInput
        value={q}
        onChange={setQ}
        placeholder={placeholder}
        onEnter={() => {
          if (matches[0]) add(matches[0].value)
          else if (custom) add(custom)
        }}
      />
      {!q && <PopoverOption multi={false} selected={lead.selected} onSelect={lead.onSelect} hint={lead.hint}>{lead.label}</PopoverOption>}
      {!q && value.length > 0 && (
        <>
          <GroupLabel>Chosen</GroupLabel>
          {value.map((v) => (
            <PopoverOption key={v} selected onSelect={() => toggle(v)}>{v}</PopoverOption>
          ))}
        </>
      )}
      {recentShown.length > 0 && (
        <>
          <GroupLabel>Recent</GroupLabel>
          {recentShown.map((v) => (
            <PopoverOption key={v} selected={false} onSelect={() => add(v)}>{v}</PopoverOption>
          ))}
        </>
      )}
      {[...groups.entries()].map(([group, entries]) => (
        <React.Fragment key={group}>
          {group && <GroupLabel>{group}</GroupLabel>}
          {entries.map((m) => (
            <PopoverOption key={m.value} selected={value.includes(m.value)} onSelect={() => toggle(m.value)}>
              {m.value}
            </PopoverOption>
          ))}
        </React.Fragment>
      ))}
      {custom && (
        <PopoverOption selected={false} onSelect={() => add(custom)}>
          Add “{custom}”
        </PopoverOption>
      )}
      {!q && <p className="px-2.5 pb-1 pt-2 type-caption">Type to search, Enter to add.</p>}
    </div>
  )
}

export function PlaceOptions({ value, onChange, recent }: { value: string[]; onChange: (v: string[]) => void; recent: string[] }) {
  return (
    <TypeaheadOptions
      vocab={PLACE_VOCAB}
      value={value}
      onChange={onChange}
      lead={{ label: ANYWHERE, hint: "No regional preference", selected: value.length === 0, onSelect: () => onChange([]) }}
      recent={recent}
      placeholder="Country or region"
    />
  )
}

export function FieldOptions({ value, auto, inferred, onChange, onAuto }: {
  value: string[]
  auto: boolean
  inferred: string[]
  onChange: (v: string[]) => void
  onAuto: () => void
}) {
  return (
    <TypeaheadOptions
      vocab={FIELD_VOCAB}
      value={auto ? [] : value}
      onChange={onChange}
      lead={{
        label: "Auto",
        hint: inferred.length ? `From your interest: ${inferred.join(", ")}` : "Read from your interest",
        selected: auto,
        onSelect: onAuto,
      }}
      placeholder="Field of study"
    />
  )
}

export function TierOptions({ value, onChange }: { value: SchoolTier[]; onChange: (v: SchoolTier[]) => void }) {
  const toggle = (t: SchoolTier) => {
    const next = value.includes(t) ? value.filter((x) => x !== t) : [...value, t]
    onChange(SCHOOL_TIERS.map((x) => x.value).filter((x) => next.includes(x)))
  }
  return (
    <div>
      <PopoverOption multi={false} selected={value.length === 0} onSelect={() => onChange([])} hint="No preference">
        Any tier
      </PopoverOption>
      {SCHOOL_TIERS.map((t) => (
        <PopoverOption key={t.value} selected={value.includes(t.value)} onSelect={() => toggle(t.value)} hint={t.hint}>
          {t.label}
        </PopoverOption>
      ))}
      {value.length > 1 && (
        <p className="px-2.5 pb-1 pt-2 type-caption">The school budget is split evenly across these tiers.</p>
      )}
    </div>
  )
}

export interface SizeValue {
  maxPrograms: number
  maxProfessors: number
  maxPerProgram: number
  flowId: string
}

export function SizeOptions({ value, onChange }: { value: SizeValue; onChange: (v: SizeValue) => void }) {
  const size = sizeOf(value)
  const [customize, setCustomize] = React.useState(size === "custom")
  const { data: plan } = useQuery({ queryKey: ["plan"], queryFn: api.getPlan, staleTime: 5 * 60_000 })
  const cap = plan?.enforced ? plan.quotas.find((q) => q.key === "professors_per_run")?.limit ?? null : null
  const maxProfessors = Math.min(RUN_DIALS.maxProfessors.max, cap ?? Infinity)
  const pick = (k: RunSize) => {
    const s = RUN_SIZES[k]
    onChange({ ...value, maxPrograms: s.maxPrograms, maxProfessors: Math.min(s.maxProfessors, maxProfessors), maxPerProgram: s.maxPerProgram })
  }
  return (
    <div>
      {(Object.keys(RUN_SIZES) as RunSize[]).map((k) => {
        const s = RUN_SIZES[k]
        return (
          <PopoverOption
            key={k}
            multi={false}
            selected={size === k}
            onSelect={() => pick(k)}
            hint={`${s.maxPrograms} schools, keeps up to ${Math.min(s.maxProfessors, maxProfessors)} professors`}
          >
            {s.label}
          </PopoverOption>
        )
      })}
      <button
        type="button"
        onClick={() => setCustomize((c) => !c)}
        aria-expanded={customize}
        className="w-full cursor-pointer rounded-md px-2.5 py-2 text-left type-meta hover:bg-accent hover:text-foreground"
      >
        {customize ? "Hide custom limits" : "Customize…"}
      </button>
      {customize && (
        <div className="space-y-2 px-2.5 pb-2">
          <Stepper label="Schools" value={value.maxPrograms} min={RUN_DIALS.maxPrograms.min} max={RUN_DIALS.maxPrograms.max} onChange={(n) => onChange({ ...value, maxPrograms: n })} />
          <Stepper label="Professors kept" value={value.maxProfessors} min={RUN_DIALS.maxProfessors.min} max={maxProfessors} onChange={(n) => onChange({ ...value, maxProfessors: n, maxPerProgram: Math.min(value.maxPerProgram, n) })} />
          <Stepper label="Faculty per school" value={value.maxPerProgram} min={RUN_DIALS.maxPerProgram.min} max={Math.min(RUN_DIALS.maxPerProgram.max, value.maxProfessors)} onChange={(n) => onChange({ ...value, maxPerProgram: n })} />
        </div>
      )}
      {cap != null && (
        <p className="px-2.5 pb-1 type-caption">Your {plan?.plan.label} plan keeps up to {cap} professors per run.</p>
      )}
    </div>
  )
}

export function FlowOptions({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const { data: flows } = useQuery({ queryKey: ["flows"], queryFn: api.listFlows, staleTime: 30_000 })
  return (
    <div>
      {(flows?.flows ?? []).map((f) => (
        <PopoverOption key={f.id} multi={false} selected={f.id === value} onSelect={() => onChange(f.id)} hint={f.builtin ? "Built in" : undefined}>
          {f.name}
        </PopoverOption>
      ))}
      <div className="px-2.5 pb-1 pt-2">
        <Link to="?settings=flows" className="text-xs text-primary hover:underline">Manage flows</Link>
      </div>
    </div>
  )
}

/** −/+ number control that can't leave its range. */
function Stepper({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (n: number) => void }) {
  const clamp = (n: number) => Math.max(min, Math.min(max, n))
  const btn = "flex size-7 cursor-pointer items-center justify-center rounded-md border border-border hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span>{label}</span>
      <span className="flex items-center gap-1.5">
        <button type="button" className={btn} aria-label={`Fewer ${label.toLowerCase()}`} disabled={value <= min} onClick={() => onChange(clamp(value - 1))}>
          <Minus className="size-3.5" />
        </button>
        <span className="w-8 text-center tabular-nums" aria-live="polite">{value}</span>
        <button type="button" className={btn} aria-label={`More ${label.toLowerCase()}`} disabled={value >= max} onClick={() => onChange(clamp(value + 1))}>
          <Plus className="size-3.5" />
        </button>
      </span>
    </div>
  )
}

export function SchoolsOptions({ fallbackProgram, onAdd }: { fallbackProgram: string; onAdd: (seeds: ProgramSeed[]) => void }) {
  const [text, setText] = React.useState("")
  const parsed = parseSchoolLines(text, fallbackProgram)
  const add = () => {
    onAdd(parsed)
    setText("")
  }
  return (
    <div className="space-y-2 px-1">
      <textarea
        aria-label="Schools, one per line"
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          // Enter is a newline here; Ctrl/Cmd+Enter adds.
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && parsed.length) {
            e.preventDefault()
            add()
          }
        }}
        placeholder={"University of Toronto — Robotics\nETH Zürich — Mechanical Engineering"}
        className="nice-scroll w-full resize-none rounded-md border border-input bg-background px-2.5 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="type-caption">
          {parsed.length ? `${parsed.length} school${parsed.length === 1 ? "" : "s"}` : ""}
        </span>
        <Button type="button" size="sm" disabled={parsed.length === 0} onClick={add}>
          Add
        </Button>
      </div>
    </div>
  )
}

export function SchoolChips({ seeds, onRemove }: { seeds: { school_name: string; program_name: string }[]; onRemove: (i: number) => void }) {
  if (seeds.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-1.5 px-3 pt-3" aria-label="Schools to research">
      {seeds.map((s, i) => (
        <li key={`${s.school_name}-${i}`} className={cn("inline-flex max-w-full items-center gap-1 rounded-md bg-muted py-1 pl-2 pr-1 text-xs")}>
          <Landmark className="size-3 shrink-0 text-muted-foreground" />
          <span className="truncate">{s.school_name}, {s.program_name}</span>
          <button
            type="button"
            aria-label={`Remove ${s.school_name}`}
            onClick={() => onRemove(i)}
            className="cursor-pointer rounded px-1 text-muted-foreground hover:bg-background hover:text-foreground"
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  )
}

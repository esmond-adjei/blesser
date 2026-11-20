import * as React from "react"
import { Link } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { Trash2, X } from "lucide-react"
import { Button, Chip, Input, Select, buttonVariants, cn } from "@blesser/ui"
import * as api from "../../lib/api"
import { CATEGORIES, CATEGORY_LABELS, KINDS, KIND_LABELS } from "../../lib/opportunities"
import {
  ALERTS,
  ALERT_LABELS,
  LEVELS,
  LEVEL_LABELS,
  describeFilters,
  filtersToParams,
  useMatchProfile,
  useSavedSearchMutations,
  useSavedSearches,
} from "../../lib/matching"
import type { AlertFrequency, MatchProfile, MatchProfileInput } from "../../lib/types"
import { useAutosave } from "../../lib/autosave"
import { toastError, toastSuccess } from "../../lib/toast"
import { SkeletonStack } from "../ui/feedback"
import { CountrySelect } from "../ui/country-select"
import { SettingRow, SettingsGroup, Switch } from "./controls"

const MAX_FIELDS = 12
const MAX_COUNTRIES = 10

function toInput(p: MatchProfile): MatchProfileInput {
  return {
    categories: p.categories,
    kinds: p.kinds,
    fields: p.fields,
    levels: p.levels,
    countries: p.countries,
    alerts: p.alerts,
    closing_soon: p.closing_soon,
  }
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

export function MatchingPanel() {
  const profile = useMatchProfile()
  const qc = useQueryClient()
  const track = useAutosave()

  async function save(next: MatchProfileInput) {
    qc.setQueryData<MatchProfile>(["match-profile"], (prev) => (prev ? { ...prev, ...next } : prev))
    const saved = await track(api.putMatchProfile(next))
    if (saved) {
      qc.setQueryData(["match-profile"], saved)
      void qc.invalidateQueries({ queryKey: ["opportunities"] })
    } else {
      void qc.invalidateQueries({ queryKey: ["match-profile"] })
    }
  }

  async function clear() {
    try {
      await api.deleteMatchProfile()
      await qc.invalidateQueries({ queryKey: ["match-profile"] })
      void qc.invalidateQueries({ queryKey: ["opportunities"] })
      toastSuccess("Cleared. For you now uses deadlines only, and match alerts are off.")
    } catch (err) {
      toastError(err, "That didn't clear. Try again.")
    }
  }

  if (!profile.data) {
    return <SkeletonStack aria-label="Loading what you're looking for" aria-busy="true" className="space-y-3" blocks={["h-24", "h-24", "h-24"]} />
  }
  const p = profile.data
  const value = toInput(p)
  const set = (patch: Partial<MatchProfileInput>) => {
    const next = { ...value, ...patch }
    if (p.saved) void save(next)
    else qc.setQueryData<MatchProfile>(["match-profile"], { ...p, ...patch })
  }

  return (
    <>
      {!p.saved ? (
        <div className="flex flex-col gap-3 rounded-lg border border-forest/40 bg-forest-soft px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
          <p className="min-w-0 flex-1 text-footnote text-ink">
            {p.countries.length || p.fields.length || p.levels.length
              ? "We filled this in from your Applicant Kit. Check it, then save to turn on For you and match alerts."
              : "Tell us what you're looking for, then save to turn on For you and match alerts."}
          </p>
          <Button size="sm" variant="primary" onClick={() => void save(value)}>
            Save
          </Button>
        </div>
      ) : null}

      <SettingsGroup title="Preferences" description="Used to order the For you list and to pick what alerts tell you about.">
        <SettingRow label="Who it's for">
          <ChipRow>
            {CATEGORIES.map((c) => (
              <Chip key={c} selected={value.categories.includes(c)} onClick={() => set({ categories: toggle(value.categories, c) })}>
                {CATEGORY_LABELS[c]}
              </Chip>
            ))}
          </ChipRow>
        </SettingRow>
        <SettingRow label="Kinds" description="Leave all off to hear about every kind.">
          <ChipRow>
            {KINDS.filter((k) => k !== "other").map((k) => (
              <Chip key={k} selected={value.kinds.includes(k)} onClick={() => set({ kinds: toggle(value.kinds, k) })}>
                {KIND_LABELS[k]}
              </Chip>
            ))}
          </ChipRow>
        </SettingRow>
        <SettingRow label="Your stage">
          <ChipRow>
            {LEVELS.map((l) => (
              <Chip key={l} selected={value.levels.includes(l)} onClick={() => set({ levels: toggle(value.levels, l) })}>
                {LEVEL_LABELS[l]}
              </Chip>
            ))}
          </ChipRow>
        </SettingRow>
        <SettingRow label="Fields and sectors" description="Your subject, sector or skills, such as public health, agritech or data science.">
          <TermInput
            values={value.fields}
            max={MAX_FIELDS}
            onChange={(fields) => set({ fields })}
          />
        </SettingRow>
        <SettingRow label="Countries you can apply from" description="Listings open only to other countries are left out. Regional and worldwide ones stay in.">
          <ChipRow>
            {value.countries.map((c) => (
              <RemovableChip key={c} label={c} onRemove={() => set({ countries: value.countries.filter((x) => x !== c) })} />
            ))}
            {value.countries.length < MAX_COUNTRIES ? (
              <CountrySelect
                value=""
                label="Add a country"
                placeholder="Add a country"
                onChange={(name) => {
                  if (name && !value.countries.includes(name)) set({ countries: [...value.countries, name] })
                }}
              />
            ) : null}
          </ChipRow>
        </SettingRow>
      </SettingsGroup>

      <SettingsGroup title="Match alerts" description="Sent to your inbox, and by push or email as set in Notifications.">
        <SettingRow
          label="New listings that fit you"
          description="Needs at least one audience, kind or field above."
          control={
            <Select
              aria-label="New match alerts"
              className="h-control-sm w-auto min-w-[110px] text-footnote"
              value={value.alerts}
              onChange={(e) => set({ alerts: e.target.value as AlertFrequency })}
            >
              {ALERTS.map((a) => (
                <option key={a} value={a}>
                  {ALERT_LABELS[a]}
                </option>
              ))}
            </Select>
          }
        />
        <SettingRow
          label="Closing soon"
          description="Once a week, listings that fit you and close within two weeks."
          control={<Switch checked={value.closing_soon} label="Weekly closing soon list" onChange={(on) => set({ closing_soon: on })} />}
        />
      </SettingsGroup>

      <SavedSearches />

      {p.saved ? (
        <SettingsGroup>
          <SettingRow
            label="Clear what you're looking for"
            description="For you goes back to deadline order and match alerts stop. Saved searches stay."
            control={
              <Button size="sm" variant="quiet" onClick={() => void clear()}>
                Clear
              </Button>
            }
          />
        </SettingsGroup>
      ) : null}
    </>
  )
}

function ChipRow({ children }: { children: React.ReactNode }) {
  return <div className="mt-2.5 flex flex-wrap items-center gap-2">{children}</div>
}

function RemovableChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <Chip tone="forest" className="h-8 pr-1.5">
      {label}
      <button
        type="button"
        aria-label={`Remove ${label}`}
        onClick={onRemove}
        className="grid size-5 cursor-pointer place-items-center rounded-full hover:bg-surface focus-visible:outline-2 focus-visible:outline-focus"
      >
        <X aria-hidden="true" className="size-3" />
      </button>
    </Chip>
  )
}

function TermInput({ values, max, onChange }: { values: string[]; max: number; onChange: (next: string[]) => void }) {
  const [draft, setDraft] = React.useState("")
  const add = () => {
    const terms = draft
      .split(",")
      .map((t) => t.trim().replace(/\s+/g, " ").slice(0, 80))
      .filter(Boolean)
    const next = [...values]
    for (const term of terms) {
      if (next.length >= max) break
      if (!next.some((v) => v.toLowerCase() === term.toLowerCase())) next.push(term)
    }
    setDraft("")
    if (next.length !== values.length) onChange(next)
  }
  return (
    <ChipRow>
      {values.map((v) => (
        <RemovableChip key={v} label={v} onRemove={() => onChange(values.filter((x) => x !== v))} />
      ))}
      {values.length < max ? (
        <Input
          aria-label="Add a field or sector"
          placeholder="Add one, then press Enter"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault()
              add()
            } else if (e.key === "Backspace" && !draft && values.length) {
              onChange(values.slice(0, -1))
            }
          }}
          onBlur={() => draft.trim() && add()}
          className="h-8 w-56 max-w-full text-footnote"
        />
      ) : null}
    </ChipRow>
  )
}

function SavedSearches() {
  const searches = useSavedSearches()
  const { update, remove } = useSavedSearchMutations()
  if (!searches.data) return null
  return (
    <SettingsGroup
      title="Saved searches"
      description={searches.data.length ? "Each one can alert you when new listings match it." : undefined}
    >
      {searches.data.length === 0 ? (
        <SettingRow
          label="No saved searches yet"
          description="Search or filter on Opportunities, then choose Save search."
          control={
            <Link to="/opportunities" className={cn(buttonVariants({ size: "sm", variant: "quiet" }))}>
              Open Opportunities
            </Link>
          }
        />
      ) : (
        searches.data.map((s) => (
          <SettingRow
            key={s.id}
            stack
            label={
              <Link to={`/opportunities?${filtersToParams(s.filters).toString()}`} className="text-link hover:underline">
                {s.name}
              </Link>
            }
            description={describeFilters(s.filters)}
            control={
              <>
                <Select
                  aria-label={`Alerts for ${s.name}`}
                  className="h-control-sm w-auto min-w-[110px] text-footnote"
                  value={s.alerts}
                  onChange={(e) =>
                    update.mutate(
                      { id: s.id, alerts: e.target.value as AlertFrequency },
                      { onError: (err) => toastError(err, "That didn't save. Try again.") },
                    )
                  }
                >
                  {ALERTS.map((a) => (
                    <option key={a} value={a}>
                      {a === "off" ? "No alerts" : `${ALERT_LABELS[a]} alerts`}
                    </option>
                  ))}
                </Select>
                <Button
                  size="sm"
                  variant="quiet"
                  aria-label={`Delete ${s.name}`}
                  icon={<Trash2 />}
                  onClick={() => remove.mutate(s.id, { onError: (err) => toastError(err, "That didn't delete. Try again.") })}
                />
              </>
            }
          />
        ))
      )}
    </SettingsGroup>
  )
}

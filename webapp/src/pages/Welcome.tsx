import * as React from "react"
import { Navigate, useNavigate, useSearchParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { Button, Chip, Logo, Wordmark } from "@blesser/ui"
import { Checkbox } from "../components/ui/checkbox"
import { CountrySelect } from "../components/ui/country-select"
import { ChipRow, RemovableChip, TermInput } from "../components/settings/MatchingPanel"
import { LoadingScreen } from "../components/feedback/LoadingScreen"
import * as api from "../lib/api"
import { useAuth } from "../lib/auth"
import { LEVELS, LEVEL_LABELS, useMatchProfile } from "../lib/matching"
import { CATEGORIES, CATEGORY_LABELS } from "../lib/opportunities"
import { toastError } from "../lib/toast"
import type { MatchProfileInput, OpportunityCategory } from "../lib/types"

const AUDIENCE_HINTS: Record<OpportunityCategory, string> = {
  startup: "Grants, accelerators and competitions for founders",
  research: "Fellowships, research grants and calls for proposals",
  student: "Scholarships, exchanges and student competitions",
}

const STEPS = 3

/** First-run setup: picks what the feed shows and fills the match profile. */
export function Welcome() {
  const { user, ready, updateUser } = useAuth()
  const [params] = useSearchParams()
  const next = params.get("next")?.startsWith("/") ? (params.get("next") as string) : "/opportunities"
  const profile = useMatchProfile()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [step, setStep] = React.useState(1)
  const [draft, setDraft] = React.useState<MatchProfileInput | null>(null)
  const [busy, setBusy] = React.useState(false)

  if (!ready) return <LoadingScreen />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(`/welcome?next=${next}`)}`} replace />
  if (user.feed_set_up && !busy) return <Navigate to={next} replace />
  if (!profile.data) return <LoadingScreen />

  const p = profile.data
  const value: MatchProfileInput = draft ?? {
    categories: p.categories,
    kinds: p.kinds,
    fields: p.fields,
    levels: p.levels,
    countries: p.countries,
    alerts: p.alerts,
    closing_soon: p.closing_soon,
  }
  const set = (patch: Partial<MatchProfileInput>) => setDraft({ ...value, ...patch })
  const toggle = <T,>(list: T[], item: T) => (list.includes(item) ? list.filter((v) => v !== item) : [...list, item])

  async function finish(save: boolean) {
    setBusy(true)
    try {
      if (save) client.setQueryData(["match-profile"], await api.putMatchProfile(value))
      updateUser(await api.finishFeedSetup())
      void client.invalidateQueries({ queryKey: ["opportunities"] })
      navigate(next, { replace: true })
    } catch (err) {
      setBusy(false)
      toastError(err, "That didn't save. Try again.")
    }
  }

  return (
    <div className="min-h-dvh bg-canvas">
      <div className="mx-auto flex min-h-dvh w-full max-w-[560px] flex-col gap-8 px-4 py-8 sm:py-12">
        <div className="flex items-center gap-1">
          <Logo title="" className="size-8" />
          <Wordmark className="text-[26px]" />
        </div>

        <div className="flex-1 space-y-6">
          {step === 1 ? (
            <>
              <Heading title="What should your feed show?" description="Pick one or more. Leave them all off to see everything." />
              <div className="divide-y divide-separator border-y border-separator">
                {CATEGORIES.map((c) => (
                  <label key={c} className="flex cursor-pointer items-center gap-3 py-3.5">
                    <Checkbox checked={value.categories.includes(c)} onCheckedChange={() => set({ categories: toggle(value.categories, c) })} />
                    <span className="min-w-0">
                      <span className="block text-callout font-semibold text-ink">{CATEGORY_LABELS[c]}</span>
                      <span className="block text-footnote text-ink-secondary">{AUDIENCE_HINTS[c]}</span>
                    </span>
                  </label>
                ))}
              </div>
            </>
          ) : step === 2 ? (
            <>
              <Heading title="Tell us about you" description="For you puts the listings that fit this first." />
              <div>
                <p className="text-callout font-semibold text-ink">Your stage</p>
                <ChipRow>
                  {LEVELS.map((l) => (
                    <Chip key={l} selected={value.levels.includes(l)} onClick={() => set({ levels: toggle(value.levels, l) })}>
                      {LEVEL_LABELS[l]}
                    </Chip>
                  ))}
                </ChipRow>
              </div>
              <div>
                <p className="text-callout font-semibold text-ink">Fields and sectors</p>
                <p className="text-footnote text-ink-secondary">Your subject, sector or skills, such as public health, agritech or data science.</p>
                <TermInput values={value.fields} max={12} onChange={(fields) => set({ fields })} />
              </div>
            </>
          ) : (
            <>
              <Heading title="Where can you apply from?" description="Listings open only to other countries are left out. Regional and worldwide ones stay in." />
              <ChipRow>
                {value.countries.map((c) => (
                  <RemovableChip key={c} label={c} onRemove={() => set({ countries: value.countries.filter((x) => x !== c) })} />
                ))}
                {value.countries.length < 10 ? (
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
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-separator pt-4">
          <Button size="sm" variant="quiet" disabled={busy} onClick={() => void finish(false)}>
            Skip for now
          </Button>
          <span className="ml-auto text-footnote text-ink-tertiary tabular-nums">
            {step} of {STEPS}
          </span>
          {step > 1 ? (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => setStep(step - 1)}>
              Back
            </Button>
          ) : null}
          {step < STEPS ? (
            <Button size="sm" variant="primary" onClick={() => setStep(step + 1)}>
              Next
            </Button>
          ) : (
            <Button size="sm" variant="primary" disabled={busy} onClick={() => void finish(true)}>
              Show my feed
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

function Heading({ title, description }: { title: string; description: string }) {
  return (
    <div className="space-y-1">
      <h1 className="type-title-2 text-ink">{title}</h1>
      <p className="text-callout text-ink-secondary">{description}</p>
    </div>
  )
}

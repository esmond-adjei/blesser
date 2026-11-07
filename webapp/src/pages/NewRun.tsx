import * as React from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "../lib/api"
import { ApiError } from "../lib/api"
import { toastError } from "../lib/toast"
import { useRuns } from "../lib/queries"
import { fmt } from "../lib/format"
import { usableRunModel, useDefaultModel, useProviderConfigs } from "../lib/providers"
import { defaultsFromRuns, inferFromInterest, normalizeDegrees, recentPlaces, type Inferred } from "../lib/runInference"
import { ANYWHERE } from "../lib/vocab"
import { runToForm } from "../components/run/runFormModel"
import { MIN_INTEREST, RunComposer, type AutoFlags, type ComposerValue } from "../components/run/RunComposer"
import { InterestSuggestions } from "../components/run/InterestSuggestions"
import { HealthBanner } from "../components/layout/AppShell"
import type { RunListItem } from "../lib/types"

const DRAFT_KEY = "graduator:new-run-draft"

const STARTERS = [
  "PhD in robot learning for dexterous manipulation, in Canada or the US",
  "Master's in public health focused on maternal health policy in Ghana",
  "PhD in computational biology: protein design with machine learning, in Europe",
]

function readDraft(): string {
  try {
    return localStorage.getItem(DRAFT_KEY) ?? ""
  } catch {
    return ""
  }
}

function writeDraft(text: string) {
  try {
    if (text.trim()) localStorage.setItem(DRAFT_KEY, text)
    else localStorage.removeItem(DRAFT_KEY)
  } catch {
    /* storage unavailable: the draft just isn't kept */
  }
}

/** New run: one composer. Degree, place and field are inferred from the sentence; changed pills stay fixed. */
export function NewRun() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [params] = useSearchParams()
  const { data: runs, isSuccess: runsLoaded } = useRuns()
  const { data: plan } = useQuery({ queryKey: ["plan"], queryFn: api.getPlan, staleTime: 60_000 })

  const [value, setValue] = React.useState<ComposerValue>(() => {
    const d = defaultsFromRuns(undefined)
    return { interest: params.get("q") ?? readDraft(), interestDocumentId: null, fields: [], seeds: [], ...d }
  })
  const [auto, setAuto] = React.useState<AutoFlags>({ degrees: true, regions: true, fields: true })
  const [inferred, setInferred] = React.useState<Inferred>(() => inferFromInterest(value.interest))
  const [busy, setBusy] = React.useState(false)
  const [nudge, setNudge] = React.useState<string | null>(null)
  // Set by "From my CV": each press reads the chosen CV again (the round
  // remounts the suggestions); cancelling or clearing sets it back to null.
  const [suggest, setSuggest] = React.useState<{ round: number; documentId: string } | null>(null)
  const providers = useProviderConfigs()
  const defaultModel = useDefaultModel()
  // The model to send: an unpicked, removed, or disabled model falls back to
  // the account default, as the picker shows it.
  const model = usableRunModel(value.model, providers.configs, !providers.isLoading && !providers.isError, defaultModel)

  // Defaults from the last run, once the list arrives ("Run again with changes"
  // below takes precedence).
  const [defaulted, setDefaulted] = React.useState(false)
  const fromId = params.get("from")
  if (runsLoaded && !defaulted && !fromId) {
    setDefaulted(true)
    const d = defaultsFromRuns(runs)
    setValue((v) => ({ ...v, ...d, degrees: auto.degrees ? d.degrees : v.degrees, regions: auto.regions ? d.regions : v.regions }))
  }

  // "Run again with changes": /new?from=<runId> starts from that
  // run's launch fields; they count as chosen, so the text won't move them.
  const { data: source } = useQuery({
    queryKey: ["run", fromId],
    queryFn: () => api.getRun(fromId as string),
    enabled: !!fromId,
  })
  const [seededFrom, setSeededFrom] = React.useState<string | null>(null)
  if (source && seededFrom !== source.id) {
    setSeededFrom(source.id)
    const f = runToForm(source)
    const listed = source.region === "(preselected list)"
    setValue({
      interest: f.interest,
      degrees: normalizeDegrees([...f.degrees, ...f.customDegrees]),
      regions: listed ? [] : f.regions.filter((r) => r !== ANYWHERE),
      fields: listed ? [] : f.fields,
      schoolTiers: f.schoolTiers,
      seeds: [],
      maxPrograms: f.maxPrograms,
      maxProfessors: f.maxProfessors,
      maxPerProgram: f.maxPerProgram,
      flowId: f.flowId,
      model: f.model,
    })
    setAuto({ degrees: false, regions: false, fields: listed || f.fields.length === 0 })
  }

  React.useEffect(() => {
    const t = window.setTimeout(() => {
      const found = inferFromInterest(value.interest)
      setInferred(found)
      setValue((v) => {
        const next = { ...v }
        if (auto.degrees && found.degrees.length) next.degrees = found.degrees
        if (auto.regions && found.places.length) next.regions = found.places
        return next.degrees === v.degrees && next.regions === v.regions ? v : next
      })
    }, 300)
    writeDraft(value.interest)
    return () => window.clearTimeout(t)
  }, [value.interest, auto.degrees, auto.regions])

  if (nudge && value.interest.trim().length >= MIN_INTEREST) setNudge(null)

  // What this run would cost against today's shared-model allowance.
  const { data: estimate } = useQuery({
    queryKey: ["run-estimate", value.maxPrograms, value.maxProfessors, value.maxPerProgram, model],
    queryFn: () =>
      api.getRunEstimate({
        max_programs: value.maxPrograms,
        max_professors: value.maxProfessors,
        max_professors_per_program: value.maxPerProgram,
        llm_provider: model,
      }),
    staleTime: 60_000,
  })
  const runQuota = plan?.enforced ? plan.quotas.find((q) => q.key === "runs_per_month") : undefined
  const outOfRuns = runQuota?.limit != null && runQuota.used != null && runQuota.used >= runQuota.limit

  async function submit() {
    if (busy) return
    const interest = value.interest.trim()
    if (!interest) return
    if (interest.length < MIN_INTEREST) {
      setNudge("Add a little more: every professor is scored against this.")
      return
    }
    // Take what the text says right now, even mid-pause.
    const found = inferFromInterest(interest)
    const degrees = auto.degrees && found.degrees.length ? found.degrees : value.degrees
    const regions = auto.regions && found.places.length ? found.places : value.regions
    const fields = auto.fields ? found.fields : value.fields
    setBusy(true)
    try {
      const shared = {
        degree_level: (degrees.length ? degrees : ["phd"]).join(", "),
        interest_statement: interest,
        interest_document_id: value.interestDocumentId ?? null,
        max_programs: value.maxPrograms,
        max_professors: value.maxProfessors,
        max_professors_per_program: value.maxPerProgram,
        flow_id: value.flowId === "standard" ? null : value.flowId,
        llm_provider: model,
      }
      const run = value.seeds.length > 0
        ? await api.createRunFromList({
            ...shared,
            programs: value.seeds.map((s) => ({
              school_name: s.school_name.trim(),
              school_country: s.school_country?.trim() || null,
              program_name: s.program_name.trim(),
              department_url: s.department_url?.trim() || null,
            })),
          })
        : await api.createRun({
            ...shared,
            region: regions.length ? regions.join(", ") : ANYWHERE,
            // Empty: the discovery brief reads the field from the interest.
            field: fields.join(", "),
            school_tiers: value.schoolTiers,
          })
      writeDraft("")
      // Show the new run now: the idle list polls only while a run is live.
      qc.setQueryData(["run", run.id], run)
      qc.setQueryData<RunListItem[]>(["runs"], (old) => [run, ...(old ?? []).filter((r) => r.id !== run.id)])
      void qc.invalidateQueries({ queryKey: ["runs"] })
      navigate(`/runs/${run.id}`)
    } catch (e2) {
      toastError(e2 instanceof ApiError && e2.status === 422 ? validationMessage(e2) : e2, "Couldn't start the run")
    } finally {
      setBusy(false)
    }
  }

  const firstRun = runsLoaded && (runs?.length ?? 0) === 0

  return (
    <div className="w-full">
      <div className="mb-6 empty:hidden">
        <HealthBanner />
      </div>
      <h1 className="mb-6 text-center text-4xl font-bold leading-tight tracking-tight">What do you want to research?</h1>
      {outOfRuns && (
        <p className="mb-3 rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm">
          You've used this month's {runQuota?.limit} runs on the {plan?.plan.label} plan. Runs start again on the 1st.
        </p>
      )}
      <RunComposer
        value={value}
        onChange={setValue}
        auto={auto}
        onAutoChange={setAuto}
        inferred={inferred}
        recentPlaces={recentPlaces(runs)}
        busy={busy}
        nudge={nudge}
        onSubmit={() => void submit()}
        onSuggest={(documentId) => setSuggest((s) => ({ round: (s?.round ?? 0) + 1, documentId }))}
      />
      {estimate?.fits === false && (
        <p className="mt-2 px-1 type-caption">
          This run needs about {fmt(estimate.estimated_tokens)} tokens
          {estimate.basis === "defaults" ? " (a first-run estimate)" : ""}, and{" "}
          {fmt(estimate.daily_allowance_left ?? 0)} are left on today's shared-model allowance, so it may
          pause partway. It carries on tomorrow, or straight away on your own model: pick one next to the send
          button, or add one in Settings &gt; Models. A smaller run size fits better.
        </p>
      )}
      <div className="mt-3 px-1">
        <InterestSuggestions
          key={suggest ? `${suggest.round}:${suggest.documentId}` : "idle"}
          autoStart={suggest !== null}
          documentId={suggest?.documentId ?? null}
          onClose={() => setSuggest(null)}
          interest={value.interest}
          onInterestChange={(interest) => setValue((v) => ({ ...v, interest, interestDocumentId: null }))}
        />
      </div>
      {firstRun && !value.interest.trim() && (
        <ul className="mt-4 flex flex-col gap-1.5 px-1" aria-label="Examples">
          {STARTERS.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => setValue((v) => ({ ...v, interest: s, interestDocumentId: null }))}
                className="w-full cursor-pointer rounded-lg px-3 py-2 text-left type-meta hover:bg-accent hover:text-foreground"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** The first field error of a 422, readably ("max_programs: …"). */
function validationMessage(err: ApiError): string {
  let detail: unknown
  try {
    detail = (JSON.parse(err.body) as { detail?: unknown }).detail
  } catch {
    detail = undefined
  }
  const first = Array.isArray(detail) ? (detail[0] as { loc?: unknown[]; msg?: string }) : undefined
  if (first?.msg) {
    const field = String(first.loc?.[first.loc.length - 1] ?? "").replace(/_/g, " ")
    return field ? `${field}: ${first.msg}` : first.msg
  }
  return "Some fields didn't pass validation. Try again."
}

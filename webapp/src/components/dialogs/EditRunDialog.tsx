import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Lock, Minus, Plus } from "lucide-react"
import * as api from "../../lib/api"
import { useRun } from "../../lib/queries"
import { RUN_SIZES, sizeOf, type RunSize } from "../../lib/runInference"
import { toastError, toastSuccess } from "../../lib/toast"
import type { Run, RunUpdate } from "../../lib/types"
import { cn } from "../../lib/utils"
import { Button } from "../ui/button"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { SkeletonStack } from "../ui/feedback"
import { FormField, FormSection } from "../ui/form"
import { Textarea } from "../ui/input"
import { RunModelSelect } from "../run/ModelPicker"
import { DEGREES, RUN_DIALS, SCHOOL_TIERS, runToForm, validateRun, type DialKey, type RunFormValue } from "../run/runFormModel"

export function EditRunDialog({
  runId, open, onOpenChange,
}: {
  runId: string
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const { data: run } = useRun(runId)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)} className="h-[min(86dvh,860px)] max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit run</DialogTitle>
          <DialogDescription>Changes apply to work queued from now on. Finished research is kept.</DialogDescription>
        </DialogHeader>
        {/* Keyed by run so the form seeds once the run has loaded. */}
        {run ? (
          <EditRunBody key={run.id} run={run} onDone={() => onOpenChange(false)} />
        ) : (
          <DialogBody>
            <SkeletonStack className="space-y-4" blocks={["h-32", "h-40", "h-16"]} />
          </DialogBody>
        )}
      </DialogContent>
    </Dialog>
  )
}

function EditRunBody({ run, onDone }: { run: Run; onDone: () => void }) {
  const qc = useQueryClient()
  const initial = React.useMemo(() => runToForm(run), [run])
  const [value, setValue] = React.useState<RunFormValue>(initial)
  const [attempted, setAttempted] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const errors = attempted ? validateRun(value, "edit", run.interest_statement, initial) : {}
  const set = <K extends keyof RunFormValue>(k: K, v: RunFormValue[K]) => setValue((prev) => ({ ...prev, [k]: v }))

  const body: RunUpdate = {}
  if (value.interest.trim() !== run.interest_statement) body.interest_statement = value.interest.trim()
  if (value.maxPrograms !== initial.maxPrograms) body.max_programs = value.maxPrograms
  if (value.maxProfessors !== initial.maxProfessors) body.max_professors = value.maxProfessors
  if (value.maxPerProgram !== initial.maxPerProgram) body.max_professors_per_program = value.maxPerProgram
  if (value.model !== initial.model) body.llm_provider = value.model
  const changes = Object.keys(body).length

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setAttempted(true)
    if (Object.keys(validateRun(value, "edit", run.interest_statement, initial)).length > 0) return
    if (changes === 0) return onDone()
    setBusy(true)
    try {
      await api.updateRun(run.id, body)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["run", run.id] }),
        qc.invalidateQueries({ queryKey: ["runs"] }),
      ])
      toastSuccess("Run updated")
      onDone()
    } catch (e2) {
      toastError(e2, "Save failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={(e) => void onSubmit(e)} noValidate className="flex min-h-0 flex-auto flex-col">
      <DialogBody className="space-y-8">
        <FormSection id="edit-interest" title="Research interest">
          <FormField
            label="What do you want to work on?"
            error={errors.interest}
            hint={!errors.interest ? "Every professor is scored against this, so be specific about methods and problems." : undefined}
          >
            <Textarea
              rows={4}
              value={value.interest}
              onChange={(e) => set("interest", e.target.value)}
              className="bg-card text-md leading-relaxed"
            />
          </FormField>
        </FormSection>

        <LimitsPanel value={value} initial={initial} onChange={setValue} error={errors.budgets} />

        <FormSection id="edit-model" title="Model" description="Used from the run's next model call.">
          <RunModelSelect value={value.model} onChange={(model) => set("model", model)} />
        </FormSection>

        <LaunchSettings value={value} />
      </DialogBody>
      <DialogFooter className="sm:items-center">
        <p className="type-caption sm:mr-auto" aria-live="polite">
          {changes === 0 ? "No changes yet" : `${changes} unsaved change${changes === 1 ? "" : "s"}`}
        </p>
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={busy || changes === 0}>{busy ? "Saving…" : "Save changes"}</Button>
      </DialogFooter>
    </form>
  )
}

function LimitsPanel({ value, initial, onChange, error }: {
  value: RunFormValue
  initial: RunFormValue
  onChange: React.Dispatch<React.SetStateAction<RunFormValue>>
  error?: string
}) {
  const { data: plan } = useQuery({ queryKey: ["plan"], queryFn: api.getPlan, staleTime: 5 * 60_000 })
  const cap = plan?.enforced ? plan.quotas.find((q) => q.key === "professors_per_run")?.limit ?? null : null
  const maxFor = (k: DialKey) =>
    k === "maxProfessors"
      ? Math.min(RUN_DIALS.maxProfessors.max, cap ?? Infinity)
      : k === "maxPerProgram"
        ? Math.min(RUN_DIALS.maxPerProgram.max, value.maxProfessors)
        : RUN_DIALS[k].max
  const size = sizeOf(value)
  const pick = (k: RunSize) => {
    const s = RUN_SIZES[k]
    const maxProfessors = Math.min(s.maxProfessors, maxFor("maxProfessors"))
    onChange((v) => ({ ...v, maxPrograms: s.maxPrograms, maxProfessors, maxPerProgram: Math.min(s.maxPerProgram, maxProfessors) }))
  }
  const setDial = (k: DialKey, n: number) =>
    onChange((v) => ({ ...v, [k]: n, ...(k === "maxProfessors" ? { maxPerProgram: Math.min(v.maxPerProgram, n) } : {}) }))

  return (
    <section aria-labelledby="edit-limits-title" className="rounded-xl bg-fill-quiet p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="edit-limits-title" className="text-sm font-semibold">Research limits</h3>
          <p className="mt-0.5 type-caption">How far the run goes. Raise them to keep researching.</p>
        </div>
        <div className="g-seg" role="group" aria-label="Run size">
          {(Object.keys(RUN_SIZES) as RunSize[]).map((k) => (
            <button key={k} type="button" aria-pressed={size === k} onClick={() => pick(k)}>
              {RUN_SIZES[k].label}
            </button>
          ))}
          <button type="button" aria-pressed={size === "custom"} disabled className="disabled:cursor-default">
            Custom
          </button>
        </div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {(Object.keys(RUN_DIALS) as DialKey[]).map((k) => (
          <Dial key={k} dial={RUN_DIALS[k]} value={value[k]} was={initial[k]} max={maxFor(k)} onChange={(n) => setDial(k, n)} />
        ))}
      </div>
      {cap != null && (
        <p className="mt-3 type-caption">Your {plan?.plan.label} plan keeps up to {cap} professors per run.</p>
      )}
      {error && <p role="alert" className="mt-3 text-xs text-destructive">{error}</p>}
    </section>
  )
}

function Dial({ dial, value, was, max, onChange }: {
  dial: (typeof RUN_DIALS)[DialKey]
  value: number
  was: number
  max: number
  onChange: (n: number) => void
}) {
  const id = React.useId()
  const clamp = (n: number) => Math.max(dial.min, Math.min(max, n))
  const step = "flex size-7 cursor-pointer items-center justify-center rounded-md text-label-secondary transition-colors hover:bg-fill hover:text-label disabled:cursor-not-allowed disabled:opacity-40"
  return (
    <div className={cn("rounded-lg bg-surface-raised p-3 shadow-xs ring-1 transition-shadow", value !== was ? "ring-2 ring-tint" : "ring-separator")}>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-compact font-medium">{dial.label}</label>
        <span className="type-caption tabular-nums">max {max}</span>
      </div>
      <div className="mt-1 flex items-center justify-between">
        <button type="button" className={step} aria-label={`Fewer: ${dial.label}`} disabled={value <= dial.min} onClick={() => onChange(clamp(value - 1))}>
          <Minus className="size-3.5" />
        </button>
        <span className="g-stat__v text-2xl" aria-live="polite">{value}</span>
        <button type="button" className={step} aria-label={`More: ${dial.label}`} disabled={value >= max} onClick={() => onChange(clamp(value + 1))}>
          <Plus className="size-3.5" />
        </button>
      </div>
      <input
        id={id}
        type="range"
        min={dial.min}
        max={max}
        value={Math.min(value, max)}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full cursor-pointer accent-primary"
      />
      <p className="mt-1 truncate type-caption">{value !== was ? `Was ${was}` : dial.hint}</p>
    </div>
  )
}

/** Discovery already ran on these, so they're read-only. */
function LaunchSettings({ value }: { value: RunFormValue }) {
  const { data } = useQuery({ queryKey: ["flows"], queryFn: api.listFlows, staleTime: 30_000 })
  const flow = data?.flows.find((f) => f.id === value.flowId)?.name
  const rows: [string, string[], string][] = [
    ["Degrees", [...value.degrees.map((d) => DEGREES.find((x) => x.value === d)?.label ?? d), ...value.customDegrees], "None"],
    ["Regions", value.regions, "Specific schools"],
    ["Fields", value.fields, "Specific schools"],
    ["School tiers", value.schoolTiers.map((t) => SCHOOL_TIERS.find((x) => x.value === t)?.label ?? t), "Any"],
  ]
  if (flow && value.flowId !== "standard") rows.push(["Flow", [flow], "Standard"])
  return (
    <section aria-labelledby="edit-launch-title" className="rounded-xl ring-1 ring-separator">
      <div className="flex items-center gap-2 border-b border-separator px-4 py-3">
        <Lock className="size-3.5 text-label-tertiary" aria-hidden />
        <h3 id="edit-launch-title" className="text-sm font-semibold">Set at launch</h3>
        <span className="ml-auto type-caption">Start a new run to search elsewhere</span>
      </div>
      <dl className="divide-y divide-separator">
        {rows.map(([label, values, empty]) => (
          <div key={label} className="flex gap-4 px-4 py-2.5">
            <dt className="w-24 shrink-0 pt-0.5 type-meta">{label}</dt>
            <dd className={cn("flex min-w-0 flex-wrap gap-1.5", values.length === 0 && "type-meta")}>
              {values.length === 0 ? empty : values.map((v) => <span key={v} className="g-tag">{v}</span>)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

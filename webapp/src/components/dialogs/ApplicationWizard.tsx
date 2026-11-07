import * as React from "react"
import { AlertTriangle, Check, Link2, Plus, X } from "lucide-react"
import {
  APPLICATION_STATUSES,
  blankApplication,
  daysUntil,
  type Application,
  type ApplicationProfessor,
  type ApplicationRequirement,
  type ApplicationStatus,
  type DegreeType,
} from "../../lib/applications"
import { useAllRunSchools, useCandidateSearch, useProgram } from "../../lib/queries"
import { Button } from "../ui/button"
import { Combobox, type ComboboxOption } from "../ui/combobox"
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog"
import { Input, Textarea } from "../ui/input"
import { FormField, FormSection, SegmentedControl } from "../ui/form"
import { Select } from "../ui/select"
import { statusLabel } from "../cards/ApplicationCards"
import { cn } from "../../lib/utils"

export type ApplicationDraft = Omit<Application, "id" | "createdAt" | "updatedAt"> & { id?: string }

/** Sections mirror the application detail page, top to bottom. */
const SECTIONS = [
  { id: "basics", label: "Basics" },
  { id: "deadline", label: "Deadline" },
  { id: "requirements", label: "Requirements" },
  { id: "funding", label: "Funding" },
  { id: "professors", label: "Professors" },
  { id: "notes", label: "Notes" },
] as const
type SectionId = (typeof SECTIONS)[number]["id"]

const COMMON_REQUIREMENTS = [
  "Statement of purpose",
  "CV / résumé",
  "3 reference letters",
  "Transcripts",
  "English test (TOEFL / IELTS)",
  "GRE",
]

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

const norm = (s: string) => s.trim().toLowerCase()

interface MergedProgram {
  key: string
  name: string
  programId: string
  runId: string
  runTitle: string
  departmentUrl: string | null
  faculty: number
}

interface MergedSchool {
  key: string
  name: string
  country: string | null
  websiteUrl: string | null
  runs: { runId: string; runTitle: string; schoolId: string }[]
  programs: MergedProgram[]
}

type Errors = Partial<Record<"school" | "program" | "link", string>>
const FIELD_ID = { school: "app-school", program: "app-program", link: "app-link" } as const

function formFrom(initial: Application | null) {
  const b = blankApplication()
  return {
    school: initial?.school ?? b.school,
    program: initial?.program ?? b.program,
    degreeType: (initial?.degreeType ?? b.degreeType) as DegreeType,
    location: initial?.location ?? b.location,
    link: initial?.link ?? b.link,
    requirements: (initial?.requirements ?? []) as ApplicationRequirement[],
    offer: initial?.offer ?? b.offer,
    feeWaiver: initial?.feeWaiver ?? b.feeWaiver,
    feeWaiverNotes: initial?.feeWaiverNotes ?? b.feeWaiverNotes,
    deadline: initial?.deadline ?? b.deadline,
    status: (initial?.status ?? b.status) as ApplicationStatus,
    professors: (initial?.professors ?? []) as ApplicationProfessor[],
    notes: initial?.notes ?? b.notes,
  }
}
type Form = ReturnType<typeof formFrom>

/** Only school and programme are required; unlinked professor names are resolved against research on save. */
export function ApplicationWizard({
  open,
  initial,
  onClose,
  onSave,
}: {
  open: boolean
  initial: Application | null
  onClose: () => void
  onSave: (draft: ApplicationDraft) => void
}) {
  const blank = React.useMemo(() => blankApplication(), [])
  const [form, setForm] = React.useState<Form>(() => formFrom(initial))
  const [reqInput, setReqInput] = React.useState("")
  // Errors show after the first save attempt, then track the form live.
  const [attempted, setAttempted] = React.useState(false)
  const [activeSection, setActiveSection] = React.useState<SectionId>("basics")
  const scrollRef = React.useRef<HTMLDivElement>(null)

  // The parent keeps a stable key so the exit transition can play; reset on open.
  const [wasOpen, setWasOpen] = React.useState(open)
  if (open !== wasOpen) {
    setWasOpen(open)
    if (open) {
      setForm(formFrom(initial))
      setReqInput("")
      setAttempted(false)
      setActiveSection("basics")
    }
  }

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
  }
  const { school, program, professors, requirements, deadline, link, location } = form

  // Schools use the per-run fan-out because the picker merges them by name below.
  const { items: scopedSchools } = useAllRunSchools(open)
  const search = useCandidateSearch(
    { status: "all", sort: "score", limit: 200, offset: 0 },
    open,
  )
  const scopedCandidates = React.useMemo(
    () => (search.data?.items ?? []).map((candidate) => ({ candidate })),
    [search.data],
  )

  const schools: MergedSchool[] = React.useMemo(() => {
    const byKey = new Map<string, MergedSchool>()
    for (const { school, runId, runTitle } of scopedSchools) {
      const key = norm(school.name)
      let merged = byKey.get(key)
      if (!merged) {
        merged = {
          key,
          name: school.name,
          country: school.country,
          websiteUrl: school.website_url,
          runs: [],
          programs: [],
        }
        byKey.set(key, merged)
      }
      merged.country ??= school.country
      merged.websiteUrl ??= school.website_url
      merged.runs.push({ runId, runTitle, schoolId: school.id })
      for (const p of school.programs) {
        const pkey = norm(p.name)
        const existing = merged.programs.find((m) => m.key === pkey)
        const entry: MergedProgram = {
          key: pkey,
          name: p.name,
          programId: p.id,
          runId,
          runTitle,
          departmentUrl: null,
          faculty: p.professors,
        }
        if (!existing) merged.programs.push(entry)
        else if (p.professors > existing.faculty) merged.programs.splice(merged.programs.indexOf(existing), 1, entry)
      }
    }
    return [...byKey.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [scopedSchools])

  const schoolMatch = schools.find((s) => s.key === norm(school)) ?? null
  const programMatch = schoolMatch?.programs.find((p) => p.key === norm(program)) ?? null

  const { data: programDetail } = useProgram(open && programMatch ? programMatch.programId : null)
  const faculty = React.useMemo(() => programDetail?.professors ?? [], [programDetail])

  const schoolOptions: ComboboxOption[] = schools.map((s) => ({
    value: s.name,
    label: s.name,
    hint: [s.country, s.runs.length > 1 ? `${s.runs.length} runs` : s.runs[0]?.runTitle].filter(Boolean).join(", "),
    badge: `${s.programs.length} prog`,
  }))

  const programOptions: ComboboxOption[] = (schoolMatch?.programs ?? []).map((p) => ({
    value: p.name,
    label: p.name,
    hint: p.runTitle,
    badge: `${p.faculty} faculty`,
  }))

  // Scored candidates first (they carry dossier links and scores), then faculty.
  const profOptions: ComboboxOption[] = React.useMemo(() => {
    const schoolKey = norm(school)
    const programKey = norm(program)
    const byKey = new Map<string, ComboboxOption & { candidateId?: string | null; professorId?: string | null }>()
    for (const { candidate } of scopedCandidates) {
      if (norm(candidate.school_name) !== schoolKey) continue
      if (programKey && norm(candidate.program_name) !== programKey) continue
      const key = norm(candidate.professor_name)
      if (byKey.has(key)) continue
      byKey.set(key, {
        value: candidate.professor_name,
        label: candidate.professor_name,
        hint: `${candidate.program_name}`,
        badge: candidate.similarity_score != null ? `${Math.round(candidate.similarity_score * 100)}%` : undefined,
        candidateId: candidate.id,
        professorId: candidate.professor_id,
      })
    }
    for (const f of faculty) {
      const key = norm(f.name)
      if (byKey.has(key)) continue
      byKey.set(key, {
        value: f.name,
        label: f.name,
        hint: `${f.papers} paper${f.papers === 1 ? "" : "s"}`,
        professorId: f.id,
      })
    }
    return [...byKey.values()].sort((a, b) => a.label.localeCompare(b.label))
  }, [scopedCandidates, faculty, school, program])

  const profLookup = React.useMemo(() => {
    const m = new Map<string, { candidateId?: string | null; professorId?: string | null }>()
    for (const { candidate } of scopedCandidates) m.set(norm(candidate.professor_name), { candidateId: candidate.id, professorId: candidate.professor_id })
    for (const f of faculty) {
      if (!m.has(norm(f.name))) m.set(norm(f.name), { professorId: f.id })
    }
    return m
  }, [scopedCandidates, faculty])

  function toggleProfessor(name: string) {
    if (professors.some((p) => norm(p.name) === norm(name))) {
      set("professors", professors.filter((p) => norm(p.name) !== norm(name)))
      return
    }
    const link = profLookup.get(norm(name))
    set("professors", [
      ...professors,
      { name, professorId: link?.professorId ?? null, candidateId: link?.candidateId ?? null, school: school.trim() || null },
    ])
  }

  function addRequirement(label = reqInput) {
    const value = label.trim()
    if (!value) return
    if (!requirements.some((r) => norm(r.label) === norm(value)))
      set("requirements", [...requirements, { label: value, done: false }])
    if (label === reqInput) setReqInput("")
  }

  const locationSuggestion = !location.trim() ? (schoolMatch?.country ?? null) : null
  const linkSuggestion = !link.trim() ? (programMatch?.departmentUrl ?? null) : null

  // Deadline: agent-indexed rows may hold free text ("Dec 15"), which a date
  // input would silently blank. Keep the text until a real date is picked.
  const legacyDeadline = deadline && !ISO_DATE.test(deadline) ? deadline : null
  const days = !legacyDeadline && deadline ? daysUntil(deadline) : null

  const filled: Record<SectionId, boolean> = {
    basics: !!school.trim() && !!program.trim(),
    deadline: !!deadline,
    requirements: requirements.length > 0,
    funding: !!form.offer.trim() || form.feeWaiver,
    professors: professors.length > 0,
    notes: !!form.notes.trim(),
  }

  function jumpTo(id: SectionId) {
    setActiveSection(id)
    document.getElementById(`app-sec-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  function onScroll() {
    const root = scrollRef.current
    if (!root) return
    const top = root.getBoundingClientRect().top
    let current: SectionId = "basics"
    for (const s of SECTIONS) {
      const el = document.getElementById(`app-sec-${s.id}`)
      if (el && el.getBoundingClientRect().top - top < 80) current = s.id
    }
    setActiveSection(current)
  }

  function validate(): Errors {
    const e: Errors = {}
    if (!school.trim()) e.school = "Pick a school, or type its name."
    if (!program.trim()) e.program = "Pick a programme, or type its name."
    if (link.trim() && !/^https?:\/\/\S+\.\S+/i.test(link.trim()))
      e.link = "Use a full web address, starting with https://"
    return e
  }

  const errors: Errors = attempted ? validate() : {}

  function submit() {
    const e = validate()
    setAttempted(true)
    const first = (Object.keys(FIELD_ID) as (keyof typeof FIELD_ID)[]).find((k) => e[k])
    if (first) {
      const el = document.getElementById(FIELD_ID[first])
      el?.scrollIntoView({ behavior: "smooth", block: "center" })
      el?.focus({ preventScroll: true })
      return
    }
    onSave({
      id: initial?.id,
      school: school.trim(),
      program: program.trim(),
      degreeType: form.degreeType,
      location: location.trim(),
      link: link.trim(),
      requirements: requirements
        .map((r) => ({ label: r.label.trim(), done: r.done }))
        .filter((r) => r.label),
      offer: form.offer.trim(),
      deadline,
      status: form.status,
      professors: professors.filter((p) => p.name.trim()).map((p) => ({ ...p, name: p.name.trim(), school: p.school?.trim() || null })),
      notes: form.notes.trim(),
      feeWaiver: form.feeWaiver,
      feeWaiverNotes: form.feeWaiverNotes.trim(),
      source: initial?.source ?? blank.source,
      runId: initial?.runId ?? blank.runId,
    })
  }

  const errorCount = Object.values(errors).filter(Boolean).length

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent
        onClose={onClose}
        className="h-[min(84dvh,860px)] max-w-4xl"
      >
        <DialogHeader>
          <DialogTitle>{initial ? "Edit application" : "New application"}</DialogTitle>
          <DialogDescription>
            {initial
              ? "Changes save to your tracker."
              : "Pick from your researched schools and professors, or type your own. Only school and programme are required."}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1">
          <nav aria-label="Form sections" className="hidden w-44 shrink-0 border-r border-border p-3 md:block">
            <ul className="space-y-0.5">
              {SECTIONS.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => jumpTo(s.id)}
                    aria-current={activeSection === s.id ? "true" : undefined}
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-compact transition-colors",
                      activeSection === s.id ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "flex size-4 shrink-0 items-center justify-center rounded-full border",
                        filled[s.id] ? "border-primary bg-primary text-primary-foreground" : "border-border",
                      )}
                    >
                      {filled[s.id] && <Check className="size-2.5" strokeWidth={3} />}
                    </span>
                    {s.label}
                    {s.id === "basics" && (errors.school || errors.program || errors.link) && (
                      <span className="ml-auto size-1.5 rounded-full bg-destructive" aria-label="Has errors" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          <DialogBody
            ref={scrollRef}
            onScroll={onScroll}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                submit()
              }
            }}
            className="px-6 py-5"
          >
            <div className="mx-auto max-w-2xl space-y-9">
              <FormSection id="app-sec-basics" title="Basics">
                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    label="School"
                    error={errors.school}
                    hint={
                      schoolMatch && schoolMatch.runs.length > 0
                        ? `From your research${schoolMatch.country ? `, ${schoolMatch.country}` : ""}`
                        : undefined
                    }
                  >
                    <Combobox
                      id={FIELD_ID.school}
                      options={schoolOptions}
                      value={schoolMatch ? school : school || null}
                      onChange={(v) => setForm((f) => ({ ...f, school: v, program: "" }))}
                      placeholder="Search or type a school…"
                      searchPlaceholder="Type to filter schools…"
                      emptyText={schoolOptions.length === 0 ? "No researched schools yet. Type to add your own." : "No match. Add it as a custom school."}
                      allowCustom
                      customLabel={(q) => `Use "${q}"`}
                      onCustom={(v) => setForm((f) => ({ ...f, school: v, program: "" }))}
                    />
                  </FormField>
                  <FormField
                    label="Programme"
                    error={errors.program}
                    hint={programMatch?.departmentUrl ? "Department page found. It's suggested as the admissions link." : undefined}
                  >
                    <Combobox
                      id={FIELD_ID.program}
                      options={programOptions}
                      value={programMatch ? program : program || null}
                      onChange={(v) => set("program", v)}
                      placeholder={schoolMatch ? "Search programmes…" : "Type a programme…"}
                      searchPlaceholder="Type to filter programmes…"
                      emptyText={schoolMatch ? "No match. Add it as a custom programme." : "Type the programme name."}
                      allowCustom
                      customLabel={(q) => `Use "${q}"`}
                      onCustom={(v) => set("program", v)}
                    />
                  </FormField>
                  <FormField label="Status">
                    <Select value={form.status} onChange={(e) => set("status", e.target.value as ApplicationStatus)}>
                      {APPLICATION_STATUSES.map((s) => (
                        <option key={s} value={s}>{statusLabel(s)}</option>
                      ))}
                    </Select>
                  </FormField>
                  <FormField label="Degree">
                    <SegmentedControl
                      label="Degree"
                      value={form.degreeType}
                      onChange={(v) => set("degreeType", v)}
                      options={[
                        { value: "PhD", label: "PhD" },
                        { value: "Masters", label: "Masters" },
                        { value: "Either", label: "Either" },
                      ]}
                    />
                  </FormField>
                  <FormField
                    label="Location"
                    optional
                    hint={locationSuggestion ? <SuggestionButton text={`Use ${locationSuggestion}`} onApply={() => set("location", locationSuggestion)} /> : undefined}
                  >
                    <Input value={location} onChange={(e) => set("location", e.target.value)} placeholder="e.g. Munich, Germany" />
                  </FormField>
                  <FormField
                    label="Admissions link"
                    optional
                    error={errors.link}
                    hint={linkSuggestion ? <SuggestionButton text="Use department page" onApply={() => set("link", linkSuggestion)} /> : undefined}
                  >
                    <Input
                      id={FIELD_ID.link}
                      type="url"
                      inputMode="url"
                      value={link}
                      onChange={(e) => set("link", e.target.value)}
                      onBlur={() => {
                        const v = link.trim()
                        // Forgiving: "ethz.ch/apply" becomes https://ethz.ch/apply.
                        if (v && !/^https?:\/\//i.test(v) && /\S+\.\S+/.test(v)) set("link", `https://${v}`)
                      }}
                      placeholder="https://…"
                    />
                  </FormField>
                </div>
              </FormSection>

              <FormSection id="app-sec-deadline" title="Deadline">
                <FormField
                  label="Application deadline"
                  optional
                  hint={
                    <span className="flex flex-wrap items-center gap-x-2">
                    {legacyDeadline ? (
                      <>Saved as text: “{legacyDeadline}”. Pick a date to get a countdown and deadline sorting.</>
                    ) : days == null ? (
                      "Drives the countdown on cards and the deadline sort."
                    ) : days < 0 ? (
                      <span className="inline-flex items-center gap-1 text-caution">
                        <AlertTriangle className="size-3.5" /> This date passed {Math.abs(days)} day{Math.abs(days) === 1 ? "" : "s"} ago.
                      </span>
                    ) : days === 0 ? (
                      "Due today."
                    ) : (
                      `In ${days} day${days === 1 ? "" : "s"}.`
                    )}
                    {deadline && (
                      <button type="button" onClick={() => set("deadline", "")} className="cursor-pointer text-primary hover:underline">
                        Clear
                      </button>
                    )}
                    </span>
                  }
                >
                  <Input
                    type="date"
                    className="max-w-xs"
                    value={legacyDeadline ? "" : deadline}
                    onChange={(e) => set("deadline", e.target.value)}
                  />
                </FormField>
              </FormSection>

              <FormSection
                id="app-sec-requirements"
                title="Requirements"
                description="What you need to submit. Tick them off from the application page."
              >
                <div className="flex gap-2">
                  <Input
                    aria-label="New requirement"
                    value={reqInput}
                    onChange={(e) => setReqInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.metaKey && !e.ctrlKey) {
                        e.preventDefault()
                        addRequirement()
                      }
                    }}
                    placeholder="Add a requirement and press Enter"
                  />
                  <Button type="button" variant="outline" onClick={() => addRequirement()} disabled={!reqInput.trim()}>
                    <Plus /> Add
                  </Button>
                </div>
                {COMMON_REQUIREMENTS.some((r) => !requirements.some((x) => norm(x.label) === norm(r))) && (
                  <div className="flex flex-wrap gap-1.5" aria-label="Common requirements">
                    {COMMON_REQUIREMENTS.filter((r) => !requirements.some((x) => norm(x.label) === norm(r))).map((r) => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => addRequirement(r)}
                        className="inline-flex cursor-pointer items-center gap-1 rounded-full ring-1 ring-separator ring-inset px-2.5 py-1 type-caption transition-colors hover:border-solid hover:bg-accent hover:text-foreground"
                      >
                        <Plus className="size-3" /> {r}
                      </button>
                    ))}
                  </div>
                )}
                {requirements.length > 0 && (
                  <ul className="-mx-2">
                    {requirements.map((r, i) => (
                      <li key={r.label} className="group flex items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-accent">
                        <input
                          type="checkbox"
                          checked={r.done}
                          onChange={() => set("requirements", requirements.map((x, j) => (j === i ? { ...x, done: !x.done } : x)))}
                          aria-label={`Mark ${r.label} as ${r.done ? "not done" : "done"}`}
                          className="size-4 shrink-0 cursor-pointer accent-primary"
                        />
                        <span className={cn("min-w-0 flex-1 truncate text-sm", r.done && "text-muted-foreground line-through")}>{r.label}</span>
                        <button
                          type="button"
                          onClick={() => set("requirements", requirements.filter((_, j) => j !== i))}
                          aria-label={`Remove ${r.label}`}
                          className="cursor-pointer rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
                        >
                          <X className="size-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </FormSection>

              <FormSection id="app-sec-funding" title="Funding">
                <FormField label="Offer / funding" optional>
                  <Textarea rows={2} value={form.offer} onChange={(e) => set("offer", e.target.value)} placeholder="e.g. Fully funded RA, decision by March" />
                </FormField>
                <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                  <input
                    type="checkbox"
                    checked={form.feeWaiver}
                    onChange={(e) => set("feeWaiver", e.target.checked)}
                    className="size-4 accent-primary"
                  />
                  The application fee can be waived
                </label>
                {form.feeWaiver && (
                  <FormField label="Waiver details" optional>
                    <Textarea rows={2} value={form.feeWaiverNotes} onChange={(e) => set("feeWaiverNotes", e.target.value)} placeholder="e.g. Request by Nov 1 with the fellowship form" />
                  </FormField>
                )}
              </FormSection>

              <FormSection
                id="app-sec-professors"
                title="Target professors"
                description="Picks link to their match and score. Typed names are matched to your research when you save."
              >
                <FormField label="Who do you want to work with?" optional>
                  <Combobox
                    multiple
                    options={profOptions}
                    values={professors.map((p) => p.name)}
                    onToggle={toggleProfessor}
                    placeholder={profOptions.length > 0 ? "Search professors…" : "Type a name…"}
                    searchPlaceholder="Type to filter professors…"
                    emptyText="No match. Add the name as typed."
                    allowCustom
                    customLabel={(q) => `Add "${q}"`}
                    onCustom={toggleProfessor}
                  />
                </FormField>
                {professors.length > 0 && (
                  <ul className="flex flex-wrap gap-1.5">
                    {professors.map((p) => {
                      const linked = !!(p.candidateId || p.professorId)
                      return (
                        <li
                          key={p.name}
                          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background py-1 pl-2.5 pr-1 text-xs font-medium"
                        >
                          {linked && <Link2 className="size-3 text-primary" aria-label="Linked to your research" />}
                          <span className="max-w-48 truncate">{p.name}</span>
                          {!linked && <span className="text-xs font-normal text-muted-foreground">links on save</span>}
                          <button
                            type="button"
                            onClick={() => toggleProfessor(p.name)}
                            aria-label={`Remove ${p.name}`}
                            className="cursor-pointer rounded-full p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                          >
                            <X className="size-3" />
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </FormSection>

              <FormSection id="app-sec-notes" title="Notes">
                <FormField label="Other notes" optional hint="Markdown works.">
                  <Textarea rows={4} value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Contacts, visit impressions, open questions…" />
                </FormField>
              </FormSection>
            </div>
          </DialogBody>
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:items-center">
          <p
            className={cn(
              "min-w-0 truncate type-caption sm:flex-1",
              errorCount === 0 && "hidden sm:block",
            )}
            aria-live="polite"
          >
            {errorCount > 0 ? (
              <span className="text-destructive">Fix {errorCount === 1 ? "the highlighted field" : `${errorCount} highlighted fields`} to save.</span>
            ) : (
              <>
                <kbd className="g-kbd">Ctrl</kbd> <kbd className="g-kbd">Enter</kbd> to save
              </>
            )}
          </p>
          <div className="flex items-center justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button data-tooltip="Save this application with its deadlines and requirements" type="button" onClick={submit}>
              <Check /> {initial ? "Save changes" : "Track application"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SuggestionButton({ text, onApply }: { text: string; onApply: () => void }) {
  return (
    <button
      type="button"
      onClick={onApply}
      className="cursor-pointer text-xs text-primary underline-offset-2 hover:underline"
    >
      {text}
    </button>
  )
}

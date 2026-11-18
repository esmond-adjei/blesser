import { Checkbox } from "../../components/ui/checkbox"
import * as React from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Star } from "lucide-react"
import { Button, buttonVariants } from "@blesser/ui"
import { SettingRow, SettingsGroup, SettingsSection } from "../../components/settings/controls"
import { EmptyState, ErrorState } from "../../components/feedback/EmptyState"
import {
  CheckField,
  KitGroup,
  KitMeterCard,
  KitRail,
  ConfirmDialog,
  FormGrid,
  KitSkeleton,
  Repeatable,
  SelectField,
  TextAreaField,
  TextField,
} from "../../components/kit/parts"
import { ApiError } from "../../lib/api"
import { STAGES, emptyTeamMember, formatBytes, kindLabel, nextSteps, normalizeProject, projectGaps } from "../../lib/kit"
import { deleteProject, kitKeys, putProject, useDocuments, useProject } from "../../lib/kitApi"
import type { Project, ProjectInput, ProjectStage } from "../../lib/kitTypes"
import { useDraft } from "../../lib/useDraft"
import { toastError, toastSuccess } from "../../lib/toast"

const SECTIONS = [
  { id: "project-basics", label: "Basics" },
  { id: "project-story", label: "Story" },
  { id: "project-team", label: "Team" },
  { id: "project-money", label: "Money" },
  { id: "project-documents", label: "Documents" },
  { id: "project-custom", label: "Custom fields" },
] as const

const CURRENCIES = ["GHS", "USD", "EUR", "GBP", "NGN", "KES", "ZAR", "XOF", "RWF", "EGP"]

export function ProjectPage() {
  const { projectId = "" } = useParams()
  const query = useProject(projectId)
  const back = (
    <Link to="/kit/projects" className="inline-flex items-center gap-1 hover:text-ink hover:underline">
      <ArrowLeft className="size-3.5" aria-hidden="true" /> All projects
    </Link>
  )

  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404
    return (
      <div className="space-y-4">
        <p className="text-footnote text-ink-secondary">{back}</p>
        {missing ? (
          <EmptyState
            title="That project isn't here"
            description="It may have been deleted."
            action={<Link to="/kit/projects" className={buttonVariants({ size: "sm" })}>See your projects</Link>}
          />
        ) : (
          <ErrorState title="The project didn't load" description="Check your connection and try again." onRetry={() => void query.refetch()} />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-footnote text-ink-secondary">{back}</p>
      {query.data ? <ProjectForm key={query.data.id} initial={query.data} /> : <KitSkeleton rows={4} />}
    </div>
  )
}

function ProjectForm({ initial }: { initial: Project }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const documents = useDocuments()
  const [completeness, setCompleteness] = React.useState(initial.completeness)
  const [deleting, setDeleting] = React.useState(false)

  const save = React.useCallback(
    async (payload: ProjectInput) => {
      const saved = await putProject(initial.id, payload)
      setCompleteness(saved.completeness)
      client.setQueryData(kitKeys.project(initial.id), saved)
      void client.invalidateQueries({ queryKey: kitKeys.projects, exact: true })
      void client.invalidateQueries({ queryKey: kitKeys.documents, exact: true })
      return saved
    },
    [client, initial.id],
  )

  const { draft: p, update: set, discard } = useDraft<ProjectInput, ProjectInput>(initial, normalizeProject, save, { canSave: (x) => !!x.name })
  const docs = documents.data ?? []
  const images = docs.filter((d) => d.kind === "logo" || d.kind === "photo" || d.content_type.startsWith("image/"))
  const hint = nextSteps(projectGaps(p))

  return (
    <SettingsSection id="kit-project" title={p.name.trim() || "Untitled project"} description={p.tagline.trim() || "Saved as you type. Forms pull from whichever project you pick."}>
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_13rem] lg:gap-10">
        <div className="min-w-0 space-y-8">
          <KitMeterCard completeness={completeness} hint={hint} />

          <KitGroup id="project-basics" title="Basics">
            <FormGrid>
              <TextField label="Name" value={p.name} onChange={(v) => set({ name: v })} maxLength={120} required hint={p.name.trim() ? undefined : "A project needs a name before it can save."} />
              <TextField label="Website" value={p.website_url} onChange={(v) => set({ website_url: v })} inputMode="url" placeholder="siwa.africa" />
              <TextField wide label="Tagline" value={p.tagline} onChange={(v) => set({ tagline: v })} maxLength={160} hint="One line on what it is and who it's for." />
              <SelectField label="Stage" value={p.stage} onChange={(v) => set({ stage: v as ProjectStage })} options={STAGES} />
              <TextField label="Sector" value={p.sector} onChange={(v) => set({ sector: v })} placeholder="Agritech" />
              <TextField label="Country" value={p.country} onChange={(v) => set({ country: v })} />
              <TextField label="City" value={p.city} onChange={(v) => set({ city: v })} />
              <TextField label="Founded" type="date" value={p.founded_on} onChange={(v) => set({ founded_on: v || null })} />
              <TextField label="Legal status" value={p.legal_status} onChange={(v) => set({ legal_status: v })} placeholder="Company limited by shares" />
              <TextField label="Registration number" value={p.registration_number} onChange={(v) => set({ registration_number: v })} />
              <SelectField
                label="Logo"
                value={p.logo_document_id ?? ""}
                onChange={(v) => set({ logo_document_id: v || null })}
                placeholder={images.length ? "None" : "Upload a logo in Documents first"}
                options={images.map((d) => ({ value: d.id, label: d.title }))}
              />
            </FormGrid>
          </KitGroup>

          <KitGroup id="project-story" title="Story" description="Write each answer once, in full. Shorter versions for word limits live in Answers.">
            <FormGrid>
              <TextAreaField label="Problem" value={p.problem} onChange={(v) => set({ problem: v })} hint="Who has it, how often, and what it costs them." />
              <TextAreaField label="Solution" value={p.solution} onChange={(v) => set({ solution: v })} />
              <TextAreaField label="Target customers" value={p.target_customers} onChange={(v) => set({ target_customers: v })} rows={3} />
              <TextAreaField label="Market size" value={p.market_size} onChange={(v) => set({ market_size: v })} rows={3} />
              <TextAreaField label="Business model" value={p.business_model} onChange={(v) => set({ business_model: v })} rows={3} />
              <TextAreaField label="Competition and advantage" value={p.competition} onChange={(v) => set({ competition: v })} rows={3} />
              <TextAreaField label="Traction" value={p.traction} onChange={(v) => set({ traction: v })} rows={3} hint="Users, revenue, pilots, partnerships: numbers with dates." />
              <TextAreaField label="Impact" value={p.impact} onChange={(v) => set({ impact: v })} rows={3} hint="Include metrics, such as farmers reached or tonnes of food saved." />
              <TextAreaField label="Why now" value={p.why_now} onChange={(v) => set({ why_now: v })} rows={3} />
            </FormGrid>
          </KitGroup>

          <KitGroup id="project-team" title="Team">
            <FormGrid>
              <TextField
                label="Team size"
                inputMode="numeric"
                value={p.team_size ?? ""}
                onChange={(v) => {
                  const digits = v.replace(/\D/g, "").slice(0, 6)
                  set({ team_size: digits ? Number(digits) : null })
                }}
                hint="Everyone, including part-time."
              />
              <div className="flex flex-col gap-2 sm:pt-6">
                <CheckField label="Women-led" checked={p.women_led} onChange={(women_led) => set({ women_led })} />
                <CheckField label="Youth-led" checked={p.youth_led} onChange={(youth_led) => set({ youth_led })} hint="Most funds mean founders under 35." />
              </div>
            </FormGrid>
            <div className="border-t border-separator">
              <Repeatable
                items={p.team}
                onChange={(team) => set({ team })}
                make={emptyTeamMember}
                noun="team member"
                empty="Founders first, then key people."
                title={(m, i) => [m.name, m.role].filter(Boolean).join(", ") || `Team member ${i + 1}`}
                render={(m, s) => (
                  <>
                    <TextField label="Name" value={m.name} onChange={(v) => s({ name: v })} />
                    <TextField label="Role" value={m.role} onChange={(v) => s({ role: v })} placeholder="CEO" />
                    <TextField label="Email" type="email" value={m.email} onChange={(v) => s({ email: v })} />
                    <TextField label="LinkedIn" value={m.linkedin_url} onChange={(v) => s({ linkedin_url: v })} inputMode="url" />
                    <TextField label="Gender" value={m.gender} onChange={(v) => s({ gender: v })} hint="Optional, for funds that ask." list="kit-team-genders" />
                    <CheckField label="Founder" checked={m.is_founder} onChange={(is_founder) => s({ is_founder })} />
                    <TextAreaField label="Bio" value={m.bio} onChange={(v) => s({ bio: v })} rows={2} />
                  </>
                )}
              />
              <datalist id="kit-team-genders">
                <option value="Woman" />
                <option value="Man" />
                <option value="Non-binary" />
                <option value="Prefer not to say" />
              </datalist>
            </div>
          </KitGroup>

          <KitGroup id="project-money" title="Money" description="Amounts as plain numbers, such as 25000. Pick the currency once for all of them.">
            <FormGrid>
              <TextField label="Currency" value={p.currency} onChange={(v) => set({ currency: v.toUpperCase() })} maxLength={3} placeholder="GHS" list="kit-currencies" />
              <datalist id="kit-currencies">
                {CURRENCIES.map((c) => <option key={c} value={c} />)}
              </datalist>
              <TextField label="Revenue, last 12 months" value={p.revenue_last_12_months} onChange={(v) => set({ revenue_last_12_months: v })} inputMode="decimal" />
              <TextField label="Funding raised so far" value={p.funding_raised} onChange={(v) => set({ funding_raised: v })} inputMode="decimal" />
              <TextField label="Amount sought" value={p.amount_sought} onChange={(v) => set({ amount_sought: v })} inputMode="decimal" />
              <TextAreaField label="Use of funds" value={p.use_of_funds} onChange={(v) => set({ use_of_funds: v })} rows={3} />
            </FormGrid>
          </KitGroup>

          <KitGroup id="project-documents" title="Documents" description="Files that belong to this project, ready to attach to its applications.">
            {documents.isLoading ? (
              <div className="p-4 sm:px-5"><div className="h-10 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" /></div>
            ) : docs.length === 0 ? (
              <SettingRow
                stack
                label="No documents yet"
                description="Upload a pitch deck, budget or registration certificate first."
                control={<Link to="/kit/documents" className={buttonVariants({ size: "sm", variant: "secondary" })}>Go to Documents</Link>}
              />
            ) : (
              <fieldset className="divide-y divide-separator">
                <legend className="sr-only">Documents linked to this project</legend>
                {docs.map((d) => {
                  const on = p.document_ids.includes(d.id)
                  return (
                    <label key={d.id} className="flex cursor-pointer items-center gap-3 px-4 py-2.5 hover:bg-highlight/60 sm:px-5">
                      <Checkbox
                        checked={on}
                        onCheckedChange={() => set({ document_ids: on ? p.document_ids.filter((x) => x !== d.id) : [...p.document_ids, d.id] })}
                        className="shrink-0"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-callout text-ink">{d.title}</span>
                        <span className="flex items-center gap-1.5 text-footnote text-ink-tertiary">
                          <span className="mr-1.5">{kindLabel(d.kind)}</span>
                          {d.is_default ? <><Star className="size-3 fill-current text-sun-ink" aria-hidden="true" /> Default</> : null}
                          <span className="ml-1.5">{formatBytes(d.size_bytes)}</span>
                        </span>
                      </span>
                    </label>
                  )
                })}
              </fieldset>
            )}
          </KitGroup>

          <KitGroup id="project-custom" title="Custom fields" description="Anything forms ask that doesn't fit above, such as a programme ID or your tax number.">
            <Repeatable
              items={p.custom_fields}
              onChange={(custom_fields) => set({ custom_fields })}
              make={() => ({ label: "", value: "" })}
              noun="field"
              title={(f, i) => f.label || `Field ${i + 1}`}
              render={(f, s) => (
                <>
                  <TextField label="Label" value={f.label} onChange={(v) => s({ label: v })} placeholder="TIN" />
                  <TextField label="Value" value={f.value} onChange={(v) => s({ value: v })} />
                </>
              )}
            />
          </KitGroup>

          <SettingsGroup title="Danger zone" danger>
            <SettingRow
              stack
              label="Delete project"
              description="Removes this project for good. Your documents and answers stay."
              control={<Button size="sm" variant="danger" onClick={() => setDeleting(true)}>Delete project</Button>}
            />
          </SettingsGroup>
        </div>

        <KitRail label="Project sections" completeness={completeness} hint={hint} sections={SECTIONS} />
      </div>

      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${p.name.trim() || "this project"}?`}
        description="Its story, team and money details go for good. Documents stay in your library."
        confirm="Delete project"
        onConfirm={async () => {
          try {
            discard()
            await deleteProject(initial.id)
            client.removeQueries({ queryKey: kitKeys.project(initial.id) })
            await client.invalidateQueries({ queryKey: kitKeys.projects })
            toastSuccess("Project deleted")
            navigate("/kit/projects")
          } catch (err) {
            toastError(err, "Couldn't delete the project")
          }
        }}
      />
    </SettingsSection>
  )
}

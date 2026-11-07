import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Plus, X } from "lucide-react"
import * as api from "../../lib/api"
import { toastError } from "../../lib/toast"
import type { ProfessorDetail } from "../../lib/types"
import { Button } from "../ui/button"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Field, Input, Textarea } from "../ui/input"
import { Select } from "../ui/select"
import { useRunSchools } from "../../lib/queries"

/** Callers pass a changing `key` so it remounts with fresh `existing` values. */
export function SchoolDialog({
  runId: fixedRunId, runOptions, open, onOpenChange, existing, onCreated,
}: {
  /** Target run. Omit and pass `runOptions` to let the user pick one. */
  runId?: string
  /** Runs to choose from (most recent first); shows a run picker. */
  runOptions?: { id: string; label: string }[]
  open: boolean
  onOpenChange: (o: boolean) => void
  existing?: { id: string; name: string; country: string | null; website_url: string | null }
  onCreated?: (school: { id: string; name: string }) => void
}) {
  const qc = useQueryClient()
  const [pickedRun, setPickedRun] = React.useState(runOptions?.[0]?.id ?? "")
  const runId = fixedRunId ?? pickedRun
  const [name, setName] = React.useState(existing?.name ?? "")
  const [country, setCountry] = React.useState(existing?.country ?? "")
  const [website, setWebsite] = React.useState(existing?.website_url ?? "")
  const [programs, setPrograms] = React.useState<{ name: string; url: string }[]>([])
  const [busy, setBusy] = React.useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      if (existing) {
        await api.updateSchool(existing.id, {
          name, country: country || null, website_url: website || null,
        })
      } else {
        const created = await api.createSchool(runId, {
          name,
          country: country || null,
          website_url: website || null,
          programs: programs
            .filter((p) => p.name.trim() !== "")
            .map((p) => ({ name: p.name.trim(), department_url: p.url.trim() || null })),
        })
        onCreated?.(created)
      }
      onOpenChange(false)
      await Promise.all([
        qc.invalidateQueries({ queryKey: existing ? ["schools"] : ["schools", runId] }),
        qc.invalidateQueries({ queryKey: ["account-schools"] }),
        qc.invalidateQueries({ queryKey: ["tasks", runId] }),
        qc.invalidateQueries({ queryKey: ["board", runId] }),
      ])
    } catch (e2) {
      toastError(e2, "Save failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>{existing ? "Edit school" : "Add school"}</DialogTitle>
          <DialogDescription>
            {existing
              ? "Update the school's details."
              : "Add a school yourself. Optional programs below each start faculty research on save."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex min-h-0 flex-auto flex-col">
          <DialogBody className="space-y-3">
            {!existing && runOptions && (
              <Field label="Run">
                <Select value={pickedRun} onChange={(e) => setPickedRun(e.target.value)} required aria-label="Run">
                  {runOptions.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                </Select>
              </Field>
            )}
            <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></Field>
            <Field label="Country"><Input value={country} onChange={(e) => setCountry(e.target.value)} /></Field>
            <Field label="Website URL"><Input value={website} onChange={(e) => setWebsite(e.target.value)} /></Field>
            {!existing && (
              <div className="space-y-2">
                <span className="text-sm font-medium">Programs (optional)</span>
                {programs.map((p, i) => (
                  <div key={i} className="flex gap-2">
                    <Input
                      value={p.name}
                      onChange={(e) => setPrograms((ps) => ps.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                      placeholder="Program name"
                      aria-label={`Program ${i + 1} name`}
                    />
                    <Input
                      value={p.url}
                      onChange={(e) => setPrograms((ps) => ps.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))}
                      placeholder="Department URL (optional)"
                      aria-label={`Program ${i + 1} URL`}
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => setPrograms((ps) => ps.filter((_, j) => j !== i))}
                      aria-label={`Remove program ${i + 1}`}
                    >
                      <X />
                    </Button>
                  </div>
                ))}
                <Button type="button" size="sm" variant="outline" onClick={() => setPrograms((ps) => [...ps, { name: "", url: "" }])}>
                  <Plus /> Add program
                </Button>
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button type="submit" disabled={busy || !name.trim() || !runId}>{busy ? "Saving..." : existing ? "Save" : "Add school"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function SocialsEditor({
  value, onChange,
}: {
  value: Array<{ label: string; url: string }>
  onChange: (next: Array<{ label: string; url: string }>) => void
}) {
  const [label, setLabel] = React.useState("")
  const [url, setUrl] = React.useState("")
  const ready = label.trim() !== "" && url.trim() !== "" && !value.some((s) => s.url === url.trim())

  function add() {
    if (!ready) return
    onChange([...value, { label: label.trim(), url: url.trim() }])
    setLabel("")
    setUrl("")
  }

  return (
    <div className="space-y-2">
      <span className="text-sm font-medium leading-none">Academic links</span>
      {value.length > 0 && (
        <ul className="space-y-1">
          {value.map((s) => (
            <li key={s.url} className="flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-sm">
              <span className="font-medium">{s.label}</span>
              <span className="min-w-0 flex-1 truncate type-caption">{s.url}</span>
              <Button aria-label="Remove academic link" type="button" size="sm" variant="ghost" onClick={() => onChange(value.filter((x) => x.url !== s.url))}>
                <X />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label (e.g. Scholar)" />
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
        <Button type="button" size="sm" variant="outline" disabled={!ready} onClick={add}>
          <Plus /> Add
        </Button>
      </div>
    </div>
  )
}

export function ProfessorEditDialog({
  prof, open, onOpenChange,
}: {
  prof: ProfessorDetail
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const qc = useQueryClient()
  const [name, setName] = React.useState(prof.name)
  const [profile, setProfile] = React.useState(prof.profile_url ?? "")
  const [email, setEmail] = React.useState(prof.email ?? "")
  const [lab, setLab] = React.useState(prof.lab_name ?? "")
  const [bio, setBio] = React.useState(prof.bio ?? "")
  const [bioSource, setBioSource] = React.useState(prof.bio_source ?? "")
  const [photo, setPhoto] = React.useState(prof.photo_url ?? "")
  const [socials, setSocials] = React.useState(prof.socials ?? [])
  const [busy, setBusy] = React.useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.updateProfessor(prof.id, { name, profile_url: profile || null, email: email || null, lab_name: lab.trim() || null, bio: bio.trim() || null, bio_source: bioSource || null, photo_url: photo.trim() || null, socials })
      onOpenChange(false)
      // The name, photo and contact also show on candidate rows and pages.
      await Promise.all(
        [["professor", prof.id], ["candidate"], ["candidates"], ["candidate-search"], ["program"], ["faculty"], ["drafts"]].map(
          (queryKey) => qc.invalidateQueries({ queryKey }),
        ),
      )
    } catch (e2) {
      toastError(e2, "Save failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader><DialogTitle>Edit professor</DialogTitle></DialogHeader>
        <form onSubmit={onSubmit} className="flex min-h-0 flex-auto flex-col">
          <DialogBody className="space-y-3">
            <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} required /></Field>
            <Field label="Profile URL"><Input value={profile} onChange={(e) => setProfile(e.target.value)} /></Field>
            <Field label="Email"><Input value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Field label="Photo URL"><Input value={photo} onChange={(e) => setPhoto(e.target.value)} placeholder="Portrait image URL" /></Field>
            <Field label="Lab / research group"><Input value={lab} onChange={(e) => setLab(e.target.value)} placeholder="The unit a PhD would join" /></Field>
            <Field label="Bio"><Textarea value={bio} onChange={(e) => setBio(e.target.value)} placeholder="Short biography" rows={4} /></Field>
            <Field label="Bio source">
              <Select value={bioSource} onChange={(e) => setBioSource(e.target.value)} placeholder="Unknown">
                <option value="faculty">Faculty page</option>
                <option value="generated">Written from papers</option>
              </Select>
            </Field>
            <SocialsEditor value={socials} onChange={setSocials} />
          </DialogBody>
          <DialogFooter>
            <Button type="submit" disabled={busy}>{busy ? "Saving..." : "Save"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Creation queues research; the dossier entry appears once they are scored. */
export function AddProfessorDialog({
  runOptions, open, onOpenChange, onCreated,
}: {
  runOptions: { id: string; label: string }[]
  open: boolean
  onOpenChange: (o: boolean) => void
  onCreated: (professor: { id: string; name: string }) => void
}) {
  const qc = useQueryClient()
  const [runId, setRunId] = React.useState(runOptions[0]?.id ?? "")
  const schools = useRunSchools(runId, false, open && runId !== "")
  const programs = (schools.data ?? []).flatMap((s) => s.programs.map((p) => ({ ...p, school: s.name })))
  const [programId, setProgramId] = React.useState("")
  const program = programs.find((p) => p.id === programId) ?? null
  const [name, setName] = React.useState("")
  const [profile, setProfile] = React.useState("")
  const [email, setEmail] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!program) return
    setBusy(true)
    try {
      const prof = await api.createProfessor(program.id, {
        name: name.trim(),
        profile_url: profile.trim() || null,
        email: email.trim() || null,
        openalex_id: null,
      })
      onOpenChange(false)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["schools", runId] }),
        qc.invalidateQueries({ queryKey: ["account-schools"] }),
        qc.invalidateQueries({ queryKey: ["program", program.id] }),
        qc.invalidateQueries({ queryKey: ["board", runId] }),
      ])
      onCreated({ id: prof.id, name: name.trim() })
    } catch (e2) {
      toastError(e2, "Couldn't add professor")
    } finally {
      setBusy(false)
    }
  }

  const noPrograms = !schools.isLoading && programs.length === 0
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Add professor</DialogTitle>
          <DialogDescription>
            Gradis pulls their papers and scores them against the run's interests. They join
            Matches as soon as scoring finishes.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex min-h-0 flex-auto flex-col">
          <DialogBody className="space-y-3">
            <Field label="Run">
              <Select value={runId} onChange={(e) => { setRunId(e.target.value); setProgramId("") }} required aria-label="Run">
                {runOptions.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </Select>
            </Field>
            <Field label="Programme">
              <Select
                value={programId}
                onChange={(e) => setProgramId(e.target.value)}
                required
                disabled={schools.isLoading || noPrograms}
                placeholder={schools.isLoading ? "Loading programmes…" : "Choose a programme"}
                aria-label="Programme"
              >
                {(schools.data ?? []).map((s) => (
                  <optgroup key={s.id} label={s.name}>
                    {s.programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </optgroup>
                ))}
              </Select>
            </Field>
            {noPrograms && (
              <p className="type-caption">
                This run has no programmes yet. Add a school with a programme from Schools first.
              </p>
            )}
            <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Daniela Rus" /></Field>
            <Field label="Faculty profile URL"><Input type="url" value={profile} onChange={(e) => setProfile(e.target.value)} placeholder="https://…" /></Field>
            <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          </DialogBody>
          <DialogFooter>
            <Button type="submit" disabled={busy || !name.trim() || !program}>{busy ? "Adding…" : "Add and research"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

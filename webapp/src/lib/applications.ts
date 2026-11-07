/** Application tracker: camelCase UI over the snake_case API, plus a one-time lift of legacy localStorage rows. */
import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "./api"
import type { ApplicationOut } from "./types"

export type ApplicationStatus = "wishlist" | "applying" | "submitted" | "interview" | "offer" | "rejected"
export type DegreeType = "PhD" | "Masters" | "Either"
export type ApplicationSource = "manual" | "agent"

export interface ApplicationRequirement {
  label: string
  done: boolean
}

export interface ApplicationProfessor {
  name: string
  /** Dossier professor id, when known. */
  professorId?: string | null
  /** Run candidate id, when known. */
  candidateId?: string | null
  school?: string | null
}

export interface Application {
  id: string
  school: string
  program: string
  degreeType: DegreeType
  location: string
  /** Grad admissions page URL. */
  link: string
  requirements: ApplicationRequirement[]
  /** Funding notes (stipend, TA/RA, fellowship). */
  offer: string
  /** ISO date (yyyy-mm-dd) or empty string when unknown. */
  deadline: string
  status: ApplicationStatus
  professors: ApplicationProfessor[]
  /** General notes, markdown. Agent-indexed rows follow the note template. */
  notes: string
  feeWaiver: boolean
  feeWaiverNotes: string
  source: ApplicationSource
  runId: string | null
  createdAt: string
  updatedAt: string
  /** School image from research, when one matches (read-only). */
  schoolImageUrl?: string | null
}

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "wishlist",
  "applying",
  "submitted",
  "interview",
  "offer",
  "rejected",
]

const LEGACY_STORAGE_KEY = "graduator.applications.v1"

interface LegacyApplication {
  id: string
  school: string
  program: string
  degreeType: DegreeType
  location: string
  link: string
  requirements: string[]
  offer: string
  deadline: string
  status: ApplicationStatus
  professors: ApplicationProfessor[]
  notes: string
  createdAt: string
  updatedAt: string
}

function loadLegacy(): LegacyApplication[] {
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as LegacyApplication[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function clearLegacy() {
  try {
    localStorage.removeItem(LEGACY_STORAGE_KEY)
  } catch {
    /* private mode — harmless, migration just retries next load */
  }
}

function toApp(out: ApplicationOut): Application {
  return {
    id: out.id,
    school: out.school,
    program: out.program,
    degreeType: (out.degree_type || "phd") === "phd" ? "PhD" : out.degree_type === "masters" ? "Masters" : out.degree_type === "either" ? "Either" : (out.degree_type as DegreeType),
    location: out.location,
    link: out.link,
    requirements: (out.requirements ?? []).map((r) => ({ label: r.label, done: !!r.done })),
    offer: out.offer,
    deadline: out.deadline,
    status: out.status as ApplicationStatus,
    professors: (out.professors ?? []).map((p) => ({
      name: p.name,
      professorId: p.professor_id,
      candidateId: p.candidate_id,
      school: p.school,
    })),
    notes: out.notes,
    feeWaiver: !!out.fee_waiver,
    feeWaiverNotes: out.fee_waiver_notes,
    source: (out.source === "agent" ? "agent" : "manual") as ApplicationSource,
    runId: out.run_id,
    createdAt: out.created_at,
    updatedAt: out.updated_at,
    schoolImageUrl: out.school_image_url ?? null,
  }
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/

function toCreate(app: Omit<Application, "id" | "createdAt" | "updatedAt">) {
  return {
    school: app.school,
    program: app.program,
    degree_type: app.degreeType === "PhD" ? "phd" : app.degreeType === "Masters" ? "masters" : app.degreeType === "Either" ? "either" : app.degreeType,
    location: app.location,
    link: app.link,
    requirements: app.requirements.map((r) => ({ label: r.label, done: r.done })),
    offer: app.offer,
    deadline: app.deadline,
    // The schedulable date deadline reminders run on; text that
    // isn't a picked date is left for the server to parse.
    ...(ISO_DAY.test(app.deadline) ? { deadline_date: app.deadline } : {}),
    status: app.status,
    professors: app.professors.map((p) => ({
      name: p.name,
      professor_id: p.professorId ?? null,
      candidate_id: p.candidateId ?? null,
      school: p.school ?? null,
    })),
    notes: app.notes,
    fee_waiver: app.feeWaiver,
    fee_waiver_notes: app.feeWaiverNotes,
  }
}

function legacyToCreate(l: LegacyApplication) {
  return {
    school: l.school,
    program: l.program,
    degree_type: l.degreeType === "PhD" ? "phd" : l.degreeType === "Masters" ? "masters" : "either",
    location: l.location,
    link: l.link,
    requirements: (l.requirements ?? []).map((label) => ({ label, done: false })),
    offer: l.offer,
    deadline: l.deadline,
    status: l.status,
    professors: (l.professors ?? []).map((p) => ({
      name: p.name,
      professor_id: p.professorId ?? null,
      candidate_id: p.candidateId ?? null,
      school: p.school ?? null,
    })),
    notes: l.notes,
    fee_waiver: false,
    fee_waiver_notes: "",
  }
}

export function blankApplication(): Omit<Application, "id" | "createdAt" | "updatedAt"> {
  return {
    school: "",
    program: "",
    degreeType: "PhD",
    location: "",
    link: "",
    requirements: [],
    offer: "",
    deadline: "",
    status: "wishlist",
    professors: [],
    notes: "",
    feeWaiver: false,
    feeWaiverNotes: "",
    source: "manual",
    runId: null,
  }
}

/** Days from today until the deadline; null when no deadline is set. */
export function daysUntil(deadline: string): number | null {
  if (!deadline) return null
  const target = new Date(`${deadline}T23:59:59`)
  if (Number.isNaN(target.getTime())) return null
  const now = new Date()
  const ms = target.getTime() - now.getTime()
  return Math.ceil(ms / 86_400_000)
}

const APPS_KEY = ["applications"]

// Module-level so every mounted hook shares one migration attempt.
let migrationAttempted = false

export function useApplications() {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: APPS_KEY,
    queryFn: api.listApplications,
  })
  const apps = React.useMemo(() => (query.data ?? []).map(toApp), [query.data])

  // One-time lift of pre-backend entries: merge anything the API doesn't
  // have yet (matched by school + program), then drop the legacy key.
  React.useEffect(() => {
    if (migrationAttempted || query.isLoading || query.isError) return
    migrationAttempted = true
    const legacy = loadLegacy()
    if (legacy.length === 0) return
    const norm = (s: string) => s.trim().toLowerCase()
    const have = new Set((query.data ?? []).map((a) => `${norm(a.school)}|${norm(a.program)}`))
    const missing = legacy.filter((l) => !have.has(`${norm(l.school)}|${norm(l.program)}`))
    if (missing.length === 0) {
      clearLegacy()
      return
    }
    void (async () => {
      let ok = true
      for (const l of missing) {
        try {
          await api.createApplication(legacyToCreate(l))
        } catch {
          // One bad row must not block the rest; the key stays so a later load retries.
          ok = false
        }
      }
      if (ok) {
        clearLegacy()
        qc.invalidateQueries({ queryKey: APPS_KEY })
      }
    })()
  }, [query.isLoading, query.isError, query.data, qc])

  const refresh = React.useCallback(
    () => qc.invalidateQueries({ queryKey: APPS_KEY }),
    [qc],
  )

  const upsert = React.useCallback(
    async (draft: Omit<Application, "id" | "createdAt" | "updatedAt"> & { id?: string }) => {
      const body = toCreate(draft)
      const saved = draft.id
        ? await api.updateApplication(draft.id, body)
        : await api.createApplication(body)
      // Best effort: the save already succeeded.
      if (draft.professors.some((p) => !p.professorId && !p.candidateId)) {
        try {
          await api.resolveApplicationProfessors(saved.id)
        } catch {
          /* links can still be resolved from the detail page */
        }
      }
      await refresh()
      return saved.id
    },
    [refresh],
  )

  const remove = React.useCallback(
    async (id: string) => {
      await api.deleteApplication(id)
      await refresh()
    },
    [refresh],
  )

  const resolveProfessors = React.useCallback(
    async (id: string) => {
      const updated = await api.resolveApplicationProfessors(id)
      await refresh()
      return toApp(updated)
    },
    [refresh],
  )

  const toggleRequirement = React.useCallback(
    async (id: string, index: number) => {
      const current = (qc.getQueryData<ApplicationOut[]>(APPS_KEY) ?? []).find((a) => a.id === id)
      if (!current) return
      const requirements = (current.requirements ?? []).map((r, i) =>
        i === index ? { label: r.label, done: !r.done } : { label: r.label, done: !!r.done },
      )
      await api.updateApplication(id, { requirements })
      await refresh()
    },
    [qc, refresh],
  )

  // Moves on the board show at once; a failed save puts the card back.
  const setStatus = React.useCallback(
    async (id: string, status: ApplicationStatus) => {
      const before = qc.getQueryData<ApplicationOut[]>(APPS_KEY)
      qc.setQueryData<ApplicationOut[]>(APPS_KEY, (rows) => rows?.map((a) => (a.id === id ? { ...a, status } : a)))
      try {
        await api.updateApplication(id, { status })
      } catch (err) {
        qc.setQueryData(APPS_KEY, before)
        throw err
      } finally {
        await refresh()
      }
    },
    [qc, refresh],
  )

  return {
    apps,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    upsert,
    remove,
    resolveProfessors,
    toggleRequirement,
    setStatus,
  }
}

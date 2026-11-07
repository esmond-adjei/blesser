import * as React from "react"
import { Plus } from "lucide-react"
import { usePreviewParam, useUrlParam } from "../lib/urlParams"
import {
  APPLICATION_STATUSES,
  daysUntil,
  useApplications,
  type Application,
  type ApplicationStatus,
} from "../lib/applications"
import { toastError } from "../lib/toast"
import { Button } from "../components/ui/button"
import { Alert, AlertDescription } from "../components/ui/feedback"
import { useDetailPanel } from "../components/layout/DetailPanel"
import { EmptyState } from "../components/feedback/EmptyState"
import { ApplicationAgenda, ApplicationBoard } from "../components/applications/ApplicationViews"
import {
  ApplicationCard,
  ApplicationDetail,
  ApplicationRowMenu,
  statusLabel,
} from "../components/cards/ApplicationCards"
import { ApplicationWizard } from "../components/dialogs/ApplicationWizard"
import { ConfirmDialog } from "../components/dialogs/ConfirmDialog"
import { ListingView, gridColumnsClass } from "../components/listing/ListingView"

/** Grad-application tracker: requirements, offers, deadlines, and professor candidates. */
export function Applications() {
  const { apps, isLoading, upsert, remove, resolveProfessors, toggleRequirement, setStatus } = useApplications()
  // Filter state lives in the URL (?q=, ?status=) so it is shareable.
  const [query, setQuery] = useUrlParam("q")
  const [statusParam, setStatusParam] = useUrlParam("status", "all")
  // Sort order lives in the URL too (?sort=).
  const [sortParam, setSortParam] = useUrlParam("sort", "deadline")
  const sort = sortParam === "school" || sortParam === "updated" ? sortParam : "deadline"
  const status = statusParam === "all" || APPLICATION_STATUSES.includes(statusParam as (typeof APPLICATION_STATUSES)[number])
    ? statusParam
    : "all"
  const [deadlineParam, setDeadlineParam] = useUrlParam("due", "all")
  const deadline = DEADLINE_WINDOWS.some((w) => w.value === deadlineParam) ? deadlineParam : "all"
  const [degreeParam, setDegreeParam] = useUrlParam("degree", "all")
  const degree = ["PhD", "Masters", "Either"].includes(degreeParam) ? degreeParam : "all"
  const [waiverParam, setWaiverParam] = useUrlParam("waiver", "all")
  const waiver = waiverParam === "yes" ? "yes" : "all"
  const [editorOpen, setEditorOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<Application | null>(null)
  const [deleting, setDeleting] = React.useState<Application | null>(null)

  const q = query.trim().toLowerCase()
  const filtered = apps.filter((a) => {
    if (status !== "all" && a.status !== status) return false
    if (degree !== "all" && a.degreeType !== degree) return false
    if (waiver === "yes" && !a.feeWaiver) return false
    if (!inWindow(a.deadline, deadline)) return false
    if (!q) return true
    return `${a.school} ${a.program} ${a.location} ${a.professors.map((p) => p.name).join(" ")}`.toLowerCase().includes(q)
  })
  // Client-side ordering. Unknown deadlines sink below dated ones.
  const sorted = [...filtered].sort((a, b) => {
    if (sort === "school") return a.school.localeCompare(b.school) || a.program.localeCompare(b.program)
    if (sort === "updated") return b.updatedAt.localeCompare(a.updatedAt)
    const da = a.deadline ? Date.parse(a.deadline) : Number.POSITIVE_INFINITY
    const db = b.deadline ? Date.parse(b.deadline) : Number.POSITIVE_INFINITY
    return da - db || a.school.localeCompare(b.school)
  })

  // Selection lives in ?preview= so the rail is deep-linkable and Back closes it.
  const { previewId: selectedId, openPreview: openApp, closePreview: closeApp } = usePreviewParam()
  const { setPanel, clearPanel } = useDetailPanel()

  const move = (app: Application, next: ApplicationStatus) => {
    setStatus(app.id, next).catch(() => toastError(`Couldn't move ${app.program || app.school}. Try again.`))
  }
  const menuFor = (a: Application) => (
    <ApplicationRowMenu app={a} onEdit={() => openEdit(a)} onDelete={() => setDeleting(a)} onMove={(next) => move(a, next)} />
  )
  // Deadlines that need attention: open applications due within a week.
  const dueSoon = apps.filter((a) => {
    const d = daysUntil(a.deadline)
    return (a.status === "wishlist" || a.status === "applying") && d !== null && d >= 0 && d < 7
  }).length

  function openCreate() {
    setEditing(null)
    setEditorOpen(true)
  }
  const openEdit = React.useCallback((app: Application) => {
    setEditing(app)
    setEditorOpen(true)
  }, [])

  // The rail appears only after the user picks a row.
  const selected = selectedId ? (apps.find((a) => a.id === selectedId) ?? null) : null
  React.useEffect(() => {
    if (selected) {
      setPanel(
        <ApplicationDetail
          key={selected.id}
          app={selected}
          onEdit={() => openEdit(selected)}
          onDelete={() => setDeleting(selected)}
          onToggleRequirement={(index) => void toggleRequirement(selected.id, index)}
          onResolve={() => resolveProfessors(selected.id)}
          size="panel"
        />,
        {
          onClose: closeApp,
          title: selected.program || selected.school || "Application",
          ref: { kind: "application", id: selected.id },
          actions: (
            <ApplicationRowMenu
              variant="header"
              app={selected}
              onEdit={() => openEdit(selected)}
              onDelete={() => setDeleting(selected)}
            />
          ),
        },
      )
    } else {
      clearPanel()
    }
  }, [selected, setPanel, clearPanel, closeApp, openEdit, resolveProfessors, toggleRequirement])

  // Unmount only: clearing in the effect above would reopen the rail after every save.
  React.useEffect(() => () => clearPanel(), [clearPanel])

  return (
    <>
      <ListingView
        title="Applications"
        search={{ value: query, onChange: setQuery, placeholder: "Search school, program, professor..." }}
        filters={[
          {
            id: "status",
            label: "Status",
            value: status,
            options: [
              { value: "all", label: "All statuses" },
              ...APPLICATION_STATUSES.map((s) => ({ value: s, label: statusLabel(s) })),
            ],
            onChange: setStatusParam,
          },
          {
            id: "due",
            label: "Deadline",
            value: deadline,
            options: DEADLINE_WINDOWS,
            onChange: setDeadlineParam,
          },
          {
            id: "degree",
            label: "Degree",
            value: degree,
            options: [
              { value: "all", label: "Any degree" },
              { value: "PhD", label: "PhD" },
              { value: "Masters", label: "Master's" },
              { value: "Either", label: "PhD or Master's" },
            ],
            onChange: setDegreeParam,
          },
          {
            id: "waiver",
            label: "Fee waiver",
            value: waiver,
            options: [
              { value: "all", label: "With or without" },
              { value: "yes", label: "Fee waiver available" },
            ],
            onChange: setWaiverParam,
          },
        ]}
        actions={
          <Button aria-label="Track a new application" size="sm" onClick={openCreate}>
            <Plus />
          </Button>
        }
        viewStorageKey="applications:view"
        availableViews={["board", "list", "grid"]}
        defaultView="board"
        gridColumns={3}
        sort={{
          value: sort,
          options: [
            { value: "deadline", label: "Deadline" },
            { value: "school", label: "School A–Z" },
            { value: "updated", label: "Recently updated" },
          ],
          onChange: setSortParam,
        }}
        items={sorted}
        renderItems={(view, { columns }) => {
          const isActive = (a: Application) => a.id === selectedId
          const open = (a: Application) => openApp(a.id)
          if (view === "board") {
            return (
              <ApplicationBoard
                apps={sorted}
                statuses={status === "all" ? APPLICATION_STATUSES : [status as ApplicationStatus]}
                isActive={isActive}
                onOpen={open}
                menuFor={menuFor}
                onMove={move}
              />
            )
          }
          if (view === "list") {
            return <ApplicationAgenda apps={sorted} isActive={isActive} onOpen={open} menuFor={menuFor} />
          }
          return (
            <ul className={`grid gap-4 ${gridColumnsClass(columns)}`}>
              {sorted.map((a) => (
                <li key={a.id} className="min-w-0">
                  <ApplicationCard
                    app={a}
                    isActive={isActive(a)}
                    onOpen={() => open(a)}
                    onEdit={() => openEdit(a)}
                    onDelete={() => setDeleting(a)}
                  />
                </li>
              ))}
            </ul>
          )
        }}
        status={isLoading ? "loading" : apps.length === 0 ? "empty" : "ready"}
        empty={
          <EmptyState
            mascot="empty-box"
            title="No applications tracked"
            description="Add the programmes you will actually apply to, with deadlines, requirements, funding notes and the professors you want to work with. Research agents index admissions details here automatically."
            action={<Button aria-label="Track a new application" size="sm" onClick={openCreate}><Plus /> Track your first application</Button>}
          />
        }
        notice={
          <>
            {dueSoon > 0 && (
              <p className="flex items-center gap-2 type-meta">
                <span className="g-pill g-pill--caution">{dueSoon} due this week</span>
                Open applications with a deadline in the next seven days.
              </p>
            )}
            {selectedId && !isLoading && !selected ? (
              <Alert variant="destructive">
                <AlertDescription>
                  Application not found. It may have been deleted. Pick another one below.
                </AlertDescription>
              </Alert>
            ) : undefined}
          </>
        }
        noMatchText="Nothing matches these filters."
      />

      <ApplicationWizard
        key={editing ? `edit-${editing.id}` : "new"}
        open={editorOpen}
        initial={editing}
        onClose={() => setEditorOpen(false)}
        onSave={(draft) => {
          void upsert(draft).then((id) => {
            setEditorOpen(false)
            openApp(id)
          })
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => { if (!o) setDeleting(null) }}
        title="Delete application?"
        description={`Removes ${deleting?.program || "this application"} at ${deleting?.school ?? ""} from your tracker. This can't be undone.`}
        loading={false}
        onConfirm={() => {
          if (deleting) {
            const id = deleting.id
            setDeleting(null)
            void remove(id).then(() => {
              if (id === selectedId) closeApp()
            })
          }
        }}
      />
    </>
  )
}

const DEADLINE_WINDOWS = [
  { value: "all", label: "Any deadline" },
  { value: "week", label: "Due in 7 days" },
  { value: "month", label: "Due in 30 days" },
  { value: "later", label: "Due later" },
  { value: "closed", label: "Closed" },
  { value: "none", label: "No deadline" },
]

function inWindow(deadline: string, window: string): boolean {
  if (window === "all") return true
  const d = daysUntil(deadline)
  if (window === "none") return d === null
  if (d === null) return false
  if (window === "closed") return d < 0
  if (window === "week") return d >= 0 && d < 7
  if (window === "month") return d >= 0 && d <= 30
  return d > 30
}

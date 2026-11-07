import * as React from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useApplications, type Application } from "../lib/applications"
import { Skeleton } from "../components/ui/feedback"
import { HealthBanner } from "../components/layout/AppShell"
import { ErrorState } from "../components/feedback/EmptyState"
import { ApplicationDetail } from "../components/cards/ApplicationCards"
import { ApplicationWizard } from "../components/dialogs/ApplicationWizard"
import { ConfirmDialog } from "../components/dialogs/ConfirmDialog"

export function ApplicationDetailPage() {
  const { appId } = useParams<{ appId: string }>()
  const navigate = useNavigate()
  const { apps, isLoading, upsert, remove, resolveProfessors, toggleRequirement } = useApplications()
  const [editorOpen, setEditorOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<Application | null>(null)
  const [deleting, setDeleting] = React.useState<Application | null>(null)

  const app = appId ? (apps.find((a) => a.id === appId) ?? null) : null

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <HealthBanner />

      {isLoading ? (
        <>
          <Skeleton className="h-10" />
          <Skeleton className="h-64" />
        </>
      ) : !app ? (
        <ErrorState
          mascot="not-found"
          title="Application not found"
          description="It may have been deleted. Pick another one in the tracker."
          action={<Link to="/applications" className="type-meta hover:text-foreground">Go to applications</Link>}
        />
      ) : (
        <ApplicationDetail
          key={app.id}
          app={app}
          size="page"
          onEdit={() => { setEditing(app); setEditorOpen(true) }}
          onDelete={() => setDeleting(app)}
          onToggleRequirement={(index) => void toggleRequirement(app.id, index)}
          onResolve={() => resolveProfessors(app.id)}
        />
      )}

      <ApplicationWizard
        key={editing ? `edit-${editing.id}` : "new"}
        open={editorOpen}
        initial={editing}
        onClose={() => setEditorOpen(false)}
        onSave={(draft) => {
          void upsert(draft).then(() => setEditorOpen(false))
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
            void remove(id).then(() => navigate("/applications"))
          }
        }}
      />
    </div>
  )
}

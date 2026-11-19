import { Link, useNavigate, useParams } from "react-router-dom"
import { ArrowUpRight, Trash2 } from "lucide-react"
import { Button, buttonVariants } from "@blesser/ui"
import { ApplicationDetail } from "../components/applications/ApplicationDetail"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { Skeleton } from "../components/ui/feedback"
import { PageHeader } from "../components/layout/PageHeader"
import { ApiError } from "../lib/api"
import { useApplication, useApplicationMutations } from "../lib/applications"
import { toastError, toastSuccess } from "../lib/toast"

export function ApplicationPage() {
  const { id } = useParams()
  const application = useApplication(id)
  const { remove } = useApplicationMutations()
  const navigate = useNavigate()
  const app = application.data

  if (application.isPending) {
    return (
      <div className="mx-auto max-w-3xl space-y-4" aria-busy="true">
        <span className="sr-only" role="status">Loading application</span>
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-72 w-full" />
      </div>
    )
  }

  if (!app) {
    const back = <Link to="/applications" className={buttonVariants({ size: "sm", variant: "secondary" })}>Back to applications</Link>
    if (application.error instanceof ApiError && application.error.status === 404) {
      return <EmptyState title="Application not found" description="It may have been removed from your tracker." action={back} />
    }
    return (
      <ErrorState
        title="Couldn't load that application"
        description="Check your connection and try again."
        action={back}
        onRetry={() => void application.refetch()}
      />
    )
  }

  return (
    <div className="bl-enter mx-auto max-w-3xl space-y-5">
      <PageHeader
        title={app.title}
        description={[app.organization, app.kind].filter(Boolean).join(", ")}
        back={<Link to="/applications" className="hover:underline">Applications</Link>}
        actions={
          <>
            {app.link ? (
              <a href={app.link} target="_blank" rel="noopener noreferrer" className={buttonVariants({ size: "sm", variant: "secondary" })}>
                Official page <ArrowUpRight />
              </a>
            ) : null}
            <Button
              size="sm"
              variant="quiet"
              className="text-critical hover:bg-critical-soft"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(app.id, {
                  onSuccess: () => {
                    toastSuccess("Removed from your applications")
                    navigate("/applications", { replace: true })
                  },
                  onError: (err) => toastError(err, "Couldn't remove it"),
                })
              }
              icon={<Trash2 />}
            >
              Remove
            </Button>
          </>
        }
      />
      <div className="rounded-xl border border-separator bg-surface p-4 sm:p-5">
        <ApplicationDetail key={app.id} app={app} />
      </div>
    </div>
  )
}

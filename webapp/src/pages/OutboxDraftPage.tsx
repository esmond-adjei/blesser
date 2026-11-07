import { Link, useParams } from "react-router-dom"
import { useOutboxDrafts, useRuns } from "../lib/queries"
import { buttonVariants } from "../components/ui/button"
import { Skeleton } from "../components/ui/feedback"
import { HealthBanner } from "../components/layout/AppShell"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { OutboxDetailPanel } from "../components/outbox/OutboxDetailPanel"

export function OutboxDraftPage() {
  const { draftId } = useParams<{ draftId: string }>()
  const { data: runs } = useRuns()
  const { items, isLoading, isError } = useOutboxDrafts()
  const match = draftId ? items.find((i) => i.draft.id === draftId) : undefined

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <HealthBanner />

      {(!runs || runs.length === 0) && !isLoading ? (
        <EmptyState
          mascot="reading"
          title="No runs yet"
          description="Drafts are written against researched professors. Start a run first."
          action={<Link to="/new" className={buttonVariants({ size: "sm" })}>New run</Link>}
        />
      ) : isLoading ? (
        <>
          <Skeleton className="h-10" />
          <Skeleton className="h-64" />
        </>
      ) : isError || !match ? (
        <ErrorState
          mascot="not-found"
          title="Draft not found"
          description="It may have been discarded. Pick another one in the outbox."
          action={<Link to="/outbox" className={buttonVariants({ size: "sm", variant: "outline" })}>Go to the outbox</Link>}
        />
      ) : (
        <OutboxDetailPanel
          key={match.draft.id}
          draft={match.draft}
          runId={match.runId}
          runTitle={match.runTitle}
          size="page"
        />
      )}
    </div>
  )
}

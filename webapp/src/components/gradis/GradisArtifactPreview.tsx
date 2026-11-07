/* eslint-disable react/only-export-components -- the preview builder and its loaders ship together */
import * as React from "react"
import { useAllRunSchools, useOutboxDrafts } from "../../lib/queries"
import { useApplications } from "../../lib/applications"
import type { PreviewRef } from "../../lib/previewRoutes"
import { SkeletonStack } from "../ui/feedback"
import { ErrorState } from "../feedback/EmptyState"
import { DossierDetailPanel } from "../dossier/DossierDetailPanel"
import { ProfessorDetailPanel } from "../dossier/ProfessorDetailPanel"
import { OutboxDetailPanel } from "../outbox/OutboxDetailPanel"
import { ApplicationDetail } from "../cards/ApplicationCards"
import { SavedProgramPanel } from "../run/SavedProgramPanel"
import { SchoolDetailView } from "../schools/SchoolDetailView"
import { CandidatePreviewActions, DraftPreviewActions } from "../layout/PreviewActions"
import { SchoolRowMenu } from "../schools/SchoolCard"
import { ApplicationEditMenu } from "../applications/ApplicationEditMenu"

function Loading() {
  return <SkeletonStack className="space-y-4" blocks={["h-10", "h-64"]} />
}

function Gone({ what }: { what: string }) {
  return (
    <ErrorState
      mascot="not-found"
      title={`${what} not found`}
      description="It may have been deleted since Gradis saved it."
    />
  )
}

function DraftPreview({ draftId }: { draftId: string }) {
  const { items, isLoading } = useOutboxDrafts()
  const match = items.find((i) => i.draft.id === draftId)
  if (isLoading) return <Loading />
  if (!match) return <Gone what="Draft" />
  return <OutboxDetailPanel draft={match.draft} runId={match.runId} runTitle={match.runTitle} />
}

/** The draft's header actions need its run, known once drafts load. */
function DraftActions({ draftId }: { draftId: string }) {
  const { items } = useOutboxDrafts()
  const match = items.find((i) => i.draft.id === draftId)
  return match ? <DraftPreviewActions draftId={draftId} runId={match.runId} /> : null
}

function ApplicationPreview({ appId }: { appId: string }) {
  const { apps, isLoading, isFetching, resolveProfessors, toggleRequirement } = useApplications()
  const app = apps.find((a) => a.id === appId)
  if (isLoading || (!app && isFetching)) return <Loading />
  if (!app) return <Gone what="Application" />
  return (
    <ApplicationDetail
      app={app}
      onEdit={() => {}}
      onDelete={() => {}}
      onToggleRequirement={(index) => void toggleRequirement(app.id, index)}
      onResolve={() => resolveProfessors(app.id)}
      size="panel"
    />
  )
}

function ApplicationActions({ appId }: { appId: string }) {
  const { apps } = useApplications()
  const app = apps.find((item) => item.id === appId)
  return app ? <ApplicationEditMenu app={app} variant="header" /> : null
}

function SchoolActions({ schoolId }: { schoolId: string }) {
  const { items } = useAllRunSchools()
  const school = items.find((item) => item.school.id === schoolId)?.school
  return school ? <SchoolRowMenu school={school} variant="header" /> : null
}

/** What the detail rail shows for a saved record: the listing's preview plus its header actions. */
export function artifactPreview(ref: PreviewRef): { node: React.ReactNode; actions?: React.ReactNode } | null {
  switch (ref.kind) {
    case "candidate":
      return {
        node: <DossierDetailPanel key={ref.id} candidateId={ref.id} />,
        actions: <CandidatePreviewActions candidateId={ref.id} />,
      }
    case "draft":
      return { node: <DraftPreview key={ref.id} draftId={ref.id} />, actions: <DraftActions draftId={ref.id} /> }
    case "application":
      return { node: <ApplicationPreview key={ref.id} appId={ref.id} />, actions: <ApplicationActions appId={ref.id} /> }
    case "program":
      return { node: <SavedProgramPanel key={ref.id} programId={ref.id} runId={ref.runId} /> }
    case "professor":
      return { node: <ProfessorDetailPanel key={ref.id} professorId={ref.id} /> }
    case "school":
      return { node: <SchoolDetailView key={ref.id} schoolId={ref.id} size="panel" />, actions: <SchoolActions schoolId={ref.id} /> }
    case "run":
      // No rail panel for runs; their cards open the page.
      return null
  }
}

import * as React from "react"
import { useParams } from "react-router-dom"
import { HealthBanner } from "../components/layout/AppShell"
import { useDetailPanel } from "../components/layout/DetailPanel"
import { SchoolDetailView } from "../components/schools/SchoolDetailView"

export function SchoolDetail() {
  const { schoolId } = useParams<{ schoolId?: string }>()
  const { clearPanel } = useDetailPanel()
  React.useEffect(() => () => clearPanel(), [clearPanel])
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <HealthBanner />
      {schoolId && <SchoolDetailView schoolId={schoolId} size="page" />}
    </div>
  )
}

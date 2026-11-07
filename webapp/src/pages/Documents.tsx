import { Navigate, useLocation, useParams } from "react-router-dom"
import { UpgradePrompt } from "../components/billing/UpgradePrompt"
import { GlobalSettingsDialog } from "../components/dialogs/SettingsDialog"
import { DocumentEditor } from "../components/documents/DocumentEditor"
import { DocumentList } from "../components/documents/DocumentList"
import { GradisProvider } from "../components/gradis/GradisProvider"

export function CvRedirect() {
  const { documentId } = useParams()
  const { search } = useLocation()
  return <Navigate replace to={`/documents${documentId ? `/${encodeURIComponent(documentId)}` : ""}${search}`} />
}

/** Outside the app shell; the editor embeds Gradis, so it brings its own GradisProvider and upgrade prompt. */
export function Documents() {
  const { documentId } = useParams()
  if (!documentId) return <DocumentList />
  return (
    <GradisProvider>
      <div className="flex h-dvh w-full overflow-hidden">
        <DocumentEditor />
        <UpgradePrompt />
        {/* The account menu in the header opens profile and settings here. */}
        <GlobalSettingsDialog />
      </div>
    </GradisProvider>
  )
}

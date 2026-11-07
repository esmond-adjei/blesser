import * as React from "react"
import { Pencil } from "lucide-react"
import { useApplications, type Application } from "../../lib/applications"
import { ApplicationWizard } from "../dialogs/ApplicationWizard"
import { MenuItem } from "../ui/menu"
import { RowMenu, type RowMenuVariant } from "../ui/row-menu"

export function ApplicationEditMenu({ app, variant = "row" }: { app: Application; variant?: RowMenuVariant }) {
  const [editing, setEditing] = React.useState(false)
  const { upsert } = useApplications()
  return (
    <>
      <RowMenu label={`Manage ${app.program || app.school}`} variant={variant}>
        <MenuItem onSelect={() => setEditing(true)}><Pencil /> Edit</MenuItem>
      </RowMenu>
      {editing && (
        <ApplicationWizard
          open
          initial={app}
          onClose={() => setEditing(false)}
          onSave={(draft) => { void upsert(draft).then(() => setEditing(false)) }}
        />
      )}
    </>
  )
}

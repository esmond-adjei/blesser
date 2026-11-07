import * as React from "react"
import { Pencil, Trash2 } from "lucide-react"
import { MenuItem } from "../ui/menu"
import { RowMenu, type RowMenuVariant } from "../ui/row-menu"
import { ConfirmDialog } from "../dialogs/ConfirmDialog"
import { useGradis } from "./GradisProvider"

/** A saved chat's rename and delete actions, in the sidebar row and the chat header. */
export function ChatMenu({
  chat,
  variant,
  onRename,
}: {
  chat: { id: string; title: string }
  variant: RowMenuVariant
  onRename: () => void
}) {
  const { remove } = useGradis()
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  return (
    <>
      <RowMenu variant={variant} label={`Manage chat ${chat.title}`}>
        <MenuItem onSelect={onRename}>
          <Pencil /> Rename
        </MenuItem>
        <MenuItem destructive onSelect={() => setConfirmDelete(true)}>
          <Trash2 /> Delete
        </MenuItem>
      </RowMenu>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this chat?"
        description="The conversation and its messages are removed for good."
        confirmLabel="Delete chat"
        destructive
        onConfirm={() => {
          setConfirmDelete(false)
          void remove(chat.id)
        }}
      />
    </>
  )
}

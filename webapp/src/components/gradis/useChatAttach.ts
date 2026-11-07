import * as React from "react"
import { uploadChatAttachment, type ChatAttachment } from "../../lib/gradis"
import { toastError } from "../../lib/toast"
import { useGradis } from "./GradisProvider"

export const MAX_ATTACHMENTS = 3
const MAX_BYTES = 2 * 1024 * 1024
export const ACCEPT = ".pdf,.docx,.md,.txt,.png,.jpg,.jpeg,.webp"

/** One hook per composer, so the button, drop and paste share one busy state. Uploads
 * finishing after the user switched chats are dropped. */
export function useChatAttach() {
  const { activeId, attachments, setAttachments } = useGradis()
  const [uploading, setUploading] = React.useState(false)
  const active = React.useRef(activeId)
  React.useLayoutEffect(() => { active.current = activeId }, [activeId])

  const attach = React.useCallback(async (files: File[]) => {
    if (!files.length || uploading) return
    if (attachments.length + files.length > MAX_ATTACHMENTS) {
      toastError(`Attach up to ${MAX_ATTACHMENTS} files per message`)
      return
    }
    const conversation = activeId
    setUploading(true)
    try {
      const added: ChatAttachment[] = []
      for (const file of files) {
        if (file.size > MAX_BYTES) throw new Error(`${file.name} is over 2 MB`)
        added.push(await uploadChatAttachment(file))
      }
      if (conversation === active.current) setAttachments((previous) => [...previous, ...added])
    } catch (error) {
      toastError(error)
    } finally {
      setUploading(false)
    }
  }, [activeId, attachments.length, setAttachments, uploading])

  return { attach, uploading, attachments, setAttachments }
}

/** The files a drop or paste carries; none for plain text. */
export function filesOf(data: DataTransfer | null): File[] {
  return data ? Array.from(data.files) : []
}

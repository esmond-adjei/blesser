import * as React from "react"
import { useLocation, useNavigate, useParams } from "react-router-dom"
import { GradisChat } from "../components/gradis/GradisChat"
import { useGradis } from "../components/gradis/GradisProvider"
import { useDetailPanel } from "../components/layout/DetailPanel"
import { storeActiveId } from "../lib/gradis"

/** Full-page Gradis chat; the URL names the conversation, so chats are linkable. */
export function GradisPage() {
  const { conversationId } = useParams<{ conversationId?: string }>()
  const { activeId, conversations, select, sending } = useGradis()
  const navigate = useNavigate()
  const location = useLocation()
  const seen = React.useRef(activeId)
  // Read after awaits, when the render an effect started from is gone.
  const latest = React.useRef(activeId)
  const convs = React.useRef(conversations)
  React.useEffect(() => {
    latest.current = activeId
    convs.current = conversations
  })

  React.useEffect(() => {
    if (!conversationId || conversationId === activeId || sending) return
    storeActiveId(conversationId)
    let cancelled = false
    void select(conversationId).then((outcome) => {
      if (cancelled || outcome !== "gone") return
      const fallback =
        (latest.current !== conversationId ? latest.current : null) ??
        convs.current.find((c) => c.id !== conversationId)?.id ??
        null
      if (fallback) {
        storeActiveId(fallback)
        void select(fallback)
        navigate(`/chat/${fallback}`, { replace: true })
      } else {
        navigate("/chat", { replace: true })
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the URL picks; activeId moving is the next effect's job
  }, [conversationId, location, sending])

  React.useEffect(() => {
    const changed = seen.current !== activeId
    seen.current = activeId
    if (!activeId) {
      if (changed && conversationId) navigate("/chat")
      return
    }
    if (activeId === conversationId) return
    if (changed || !conversationId) navigate(`/chat/${activeId}`, { replace: !conversationId })
  }, [activeId, conversationId, navigate])

  const { clearPanel } = useDetailPanel()
  React.useEffect(() => () => clearPanel(), [clearPanel])

  return <GradisChat variant="page" />
}

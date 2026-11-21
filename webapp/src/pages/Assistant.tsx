import { useCallback } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { assistantHref } from "../lib/assistant"
import { useAuth } from "../lib/auth"
import { AssistantChat } from "../components/assistant/AssistantChat"

export function Assistant() {
  const { user } = useAuth()
  const { chatId } = useParams()
  const navigate = useNavigate()
  const change = useCallback((id?: string) => navigate(id ? assistantHref(id) : "/assistant"), [navigate])
  return <AssistantChat key={user?.id} userId={user?.id ?? ""} chatId={chatId} onChatChange={change} variant="page" />
}

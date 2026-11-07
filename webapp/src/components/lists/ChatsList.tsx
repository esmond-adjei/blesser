import * as React from "react"
import { Link, useMatch } from "react-router-dom"
import { MessageCircle } from "lucide-react"
import { useGradis } from "../gradis/GradisProvider"
import { ChatMenu } from "../gradis/ChatMenu"
import { LoadMore } from "../ui/LoadMore"
import { RenameInput } from "../ui/RenameInput"
import { cn } from "../../lib/utils"
import type { GradisConversation } from "../../lib/gradis"

export function ChatsList() {
  const { conversations, hasMoreConversations, loadingMoreConversations, loadMoreConversations } = useGradis()
  const loadMore = React.useCallback(() => void loadMoreConversations(), [loadMoreConversations])
  const match = useMatch("/chat/:conversationId")
  const current = match?.params.conversationId ?? null

  return (
    <div className="flex-1 space-y-0.5 px-2 pb-2">
      {conversations.length === 0 && (
        <p className="px-2 py-2 type-caption">No chats yet.</p>
      )}
      {conversations.map((c) => (
        <ChatRow key={c.id} chat={c} active={c.id === current} />
      ))}
      <LoadMore hasMore={hasMoreConversations} loading={loadingMoreConversations} onLoad={loadMore} />
    </div>
  )
}

function ChatRow({ chat, active }: { chat: GradisConversation; active: boolean }) {
  const { rename } = useGradis()
  const [editing, setEditing] = React.useState(false)

  if (editing) {
    return (
      <RenameInput
        value={chat.title}
        label="Rename chat"
        maxLength={80}
        onDone={(next) => {
          setEditing(false)
          if (next?.trim() && next.trim() !== chat.title) void rename(chat.id, next)
        }}
        className="h-9 w-full rounded-md border border-ring bg-background px-3 text-sm outline-none"
      />
    )
  }

  return (
    <div className="group relative">
      <Link
        to={`/chat/${chat.id}`}
        data-tooltip={chat.title}
        aria-current={active ? "page" : undefined}
        className={cn(
          "relative flex h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors",
          active
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        )}
      >
        <MessageCircle className="size-3.5 shrink-0" />
        <span className={cn("text-fade min-w-0 flex-1", active && "font-medium")}>{chat.title}</span>
        {chat.has_pending && (
          <span
            role="img"
            aria-label="Waiting for your approval"
            data-tooltip="Waiting for your approval"
            className="absolute right-0 size-1.5 shrink-0 rounded-full bg-ring"
          />
        )}
      </Link>
      <ChatMenu variant="sidebar" chat={chat} onRename={() => setEditing(true)} />
    </div>
  )
}

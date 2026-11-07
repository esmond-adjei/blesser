import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import { ChevronRight, Plus } from "lucide-react"
import { RunsList } from "../lists/RunsList"
import { ChatsList } from "../lists/ChatsList"
import { useGradis } from "../gradis/GradisProvider"
import { cn } from "../../lib/utils"

function loadOpen(key: string): boolean {
  try {
    return localStorage.getItem(key) !== "0"
  } catch {
    return true
  }
}

/** A section's collapsed state, remembered per browser. */
function useSectionOpen(key: string) {
  const [open, setOpen] = React.useState(() => loadOpen(key))
  const toggle = React.useCallback(() => {
    setOpen((prev) => {
      try {
        localStorage.setItem(key, prev ? "0" : "1")
      } catch {
        /* the section still toggles for this visit */
      }
      return !prev
    })
  }, [key])
  return [open, toggle] as const
}

function Section({
  label,
  open,
  onToggle,
  action,
  children,
}: {
  label: string
  open: boolean
  onToggle: () => void
  action: React.ReactNode
  /** Grow no taller than the list itself, leaving spare height to the other section. */
  children: React.ReactNode
}) {
  return (
    <section
      aria-label={label}
      className={cn("flex flex-col max-h-max", open ? "flex-1 basis-0" : "flex-none")}
    >
      <div className="flex flex-none items-center gap-1 px-3 pb-1">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-1 px-2.5 py-1 text-xs font-semibold text-label-tertiary uppercase hover:text-label-secondary"
        >
          {label}
          <ChevronRight className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")} />
        </button>
        {action}
      </div>
      {open && <div className="flex flex-col">{children}</div>}
    </section>
  )
}

const actionClass =
  "cursor-pointer rounded-md p-1 text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"

/** Open sections split the space; a short one yields its unused space to the other. */
export function SidebarListings({ activeRunId }: { activeRunId: string | null }) {
  const [runsOpen, toggleRuns] = useSectionOpen("graduator.sidebar.runs")
  const [chatsOpen, toggleChats] = useSectionOpen("graduator.sidebar.chats")
  const { newChat, sending } = useGradis()
  const navigate = useNavigate()

  function startChat() {
    // An unsaved new chat on the chat page; it gets its URL once sent.
    if (newChat()) navigate("/chat")
  }

  return (
    <div className="py-2 flex flex-col gap-2">
      <Section
        label="Runs"
        open={runsOpen}
        onToggle={toggleRuns}
        action={
          <Link to="/new" data-tooltip="New run" aria-label="New run" className={actionClass}>
            <Plus className="size-3.5" />
          </Link>
        }
      >
        <RunsList activeRunId={activeRunId} />
      </Section>
      <Section
        label="Chats"
        open={chatsOpen}
        onToggle={toggleChats}
        action={
          <button
            type="button"
            onClick={() => void startChat()}
            disabled={sending}
            data-tooltip="New chat"
            aria-label="New chat"
            className={cn(actionClass, "disabled:cursor-default disabled:opacity-50")}
          >
            <Plus className="size-3.5" />
          </button>
        }
      >
        <ChatsList />
      </Section>
    </div>
  )
}

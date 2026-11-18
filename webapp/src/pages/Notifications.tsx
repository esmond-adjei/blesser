import * as React from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlarmClock, Bell, CheckCheck, CircleAlert, Radar, Settings, Trash2 } from "lucide-react"
import { Button, cn } from "@blesser/ui"
import * as api from "../lib/api"
import type { AppNotification } from "../lib/api"
import { formatAgo } from "../lib/format"
import { toastError } from "../lib/toast"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { PageHeader, Segmented } from "../components/layout/PageHeader"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../components/ui/menu"

const KIND: Record<string, { icon: typeof Bell; tile: string }> = {
  scan_finished: { icon: Radar, tile: "bg-forest-soft text-link" },
  scan_attention: { icon: CircleAlert, tile: "bg-caution-soft text-caution" },
  deadline: { icon: AlarmClock, tile: "bg-sun-soft text-sun-ink" },
}

function dayGroup(iso: string): string {
  const then = new Date(iso.endsWith("Z") ? iso : `${iso}Z`)
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const days = Math.floor((start.getTime() - then.getTime()) / 86_400_000) + 1
  if (then >= start) return "Today"
  if (days <= 1) return "Yesterday"
  if (days <= 7) return "This week"
  return "Earlier"
}

export function Notifications() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [filter, setFilter] = React.useState<"all" | "unread">("all")
  const inbox = useQuery({ queryKey: ["notifications"], queryFn: api.listNotifications, refetchInterval: 60_000 })
  const refresh = () => void client.invalidateQueries({ queryKey: ["notifications"] })
  const readAll = useMutation({ mutationFn: api.markAllNotificationsRead, onSuccess: refresh, onError: (e) => toastError(e) })
  const clear = useMutation({ mutationFn: api.clearNotifications, onSuccess: refresh, onError: (e) => toastError(e) })
  const items = (inbox.data?.items ?? []).filter((n) => filter === "all" || !n.read_at)
  const unread = inbox.data?.unread ?? 0

  const groups: { label: string; items: AppNotification[] }[] = []
  for (const n of items) {
    const label = dayGroup(n.created_at)
    const last = groups.at(-1)
    if (last?.label === label) last.items.push(n)
    else groups.push({ label, items: [n] })
  }

  const open = async (n: AppNotification) => {
    if (!n.read_at) {
      await api.markNotificationRead(n.id).catch(() => undefined)
      refresh()
    }
    if (n.link) navigate(n.link)
  }

  return (
    <div className="bl-enter min-w-0 space-y-5">
      <PageHeader
        title="Notifications"
        description="Scan results and deadline reminders, newest first."
        actions={
          <div className="flex items-center gap-1">
            {unread ? <Button size="sm" variant="quiet" icon={<CheckCheck />} disabled={readAll.isPending} onClick={() => readAll.mutate()}>Mark all read</Button> : null}
            <ActionMenuButton
              label="Notification actions"
              actions={[
                { label: "Notification settings", icon: <Settings />, onSelect: () => navigate("/settings/notifications") },
                { kind: "separator" },
                { label: "Clear all", icon: <Trash2 />, danger: true, disabled: !inbox.data?.items.length, onSelect: () => clear.mutate() },
              ]}
            />
          </div>
        }
      />
      <Segmented
        label="Show"
        value={filter}
        onChange={setFilter}
        options={[{ value: "all", label: "All" }, { value: "unread", label: "Unread", count: unread }]}
      />
      {inbox.isLoading ? (
        <div className="space-y-2">{Array.from({ length: 4 }, (_, i) => <div key={i} className="h-16 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />)}</div>
      ) : inbox.isError ? (
        <ErrorState title="Your notifications didn't load" description="Try again in a moment." onRetry={() => void inbox.refetch()} />
      ) : !items.length ? (
        <EmptyState
          title={filter === "unread" ? "You're all caught up" : "No notifications yet"}
          description="We'll tell you here when a scan finishes or a deadline is close."
        />
      ) : (
        <div className="space-y-5">
          {groups.map((group) => (
            <section key={group.label} aria-label={group.label} className="space-y-1.5">
              <h2 className="text-caption text-ink-tertiary">{group.label}</h2>
              <ul className="overflow-hidden rounded-lg border border-separator bg-surface">
                {group.items.map((n, i) => <NotificationRow key={n.id} n={n} index={i} onOpen={() => void open(n)} onChange={refresh} />)}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

function NotificationRow({ n, index, onOpen, onChange }: { n: AppNotification; index: number; onOpen: () => void; onChange: () => void }) {
  const kind = KIND[n.kind] ?? { icon: Bell, tile: "bg-surface-sunk text-ink-secondary" }
  const unread = !n.read_at
  const actions: MenuAction[] = [
    ...(unread ? [{ label: "Mark read", icon: <CheckCheck />, onSelect: () => void api.markNotificationRead(n.id).then(onChange) }] : []),
    { label: "Delete", icon: <Trash2 />, danger: true, onSelect: () => void api.deleteNotification(n.id).then(onChange).catch((e) => toastError(e)) },
  ]
  return (
    <ActionContextMenu actions={actions}>
      <li style={{ "--i": index } as React.CSSProperties} className="bl-enter relative grid grid-cols-[36px_minmax(0,1fr)_auto] items-start gap-3 border-t border-separator px-4 py-3 first:border-t-0 hover:bg-highlight">
        <span className={cn("grid size-9 place-items-center rounded-full", kind.tile)}>
          <kind.icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
        </span>
        <button type="button" onClick={onOpen} className="min-w-0 cursor-pointer text-left after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-focus">
          <span className="flex items-center gap-2">
            <span className={cn("truncate text-callout", unread ? "font-semibold text-ink" : "text-ink-secondary")}>{n.title}</span>
            {unread ? <span className="size-2 shrink-0 rounded-full bg-sun" role="img" aria-label="Unread" /> : null}
          </span>
          {n.body ? <span className="mt-0.5 line-clamp-2 block text-footnote text-ink-secondary">{n.body}</span> : null}
          <span className="mt-0.5 block text-caption font-medium text-ink-tertiary">{formatAgo(n.created_at)}</span>
        </button>
        <ActionMenuButton actions={actions} label={`More for ${n.title}`} className="relative z-10 -my-1" />
      </li>
    </ActionContextMenu>
  )
}

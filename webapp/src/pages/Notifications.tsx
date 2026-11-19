import * as React from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlarmClock, Bell, CheckCheck, CircleAlert, ListChecks, Radar, Settings, Trash2 } from "lucide-react"
import { Button, cn } from "@blesser/ui"
import * as api from "../lib/api"
import type { AppNotification } from "../lib/api"
import { formatAgo } from "../lib/format"
import { toastError } from "../lib/toast"
import { Checkbox } from "../components/ui/checkbox"
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/ui/alert-dialog"
import { DialogFooter, DialogHeader } from "../components/ui/dialog"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { Segmented } from "../components/layout/PageHeader"
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
  const [selecting, setSelecting] = React.useState(false)
  const [selected, setSelected] = React.useState<Set<string>>(() => new Set())
  const [confirm, setConfirm] = React.useState<"selected" | "all" | null>(null)
  const inbox = useQuery({ queryKey: ["notifications"], queryFn: api.listNotifications, refetchInterval: 60_000 })
  const refresh = () => void client.invalidateQueries({ queryKey: ["notifications"] })
  const readAll = useMutation({ mutationFn: api.markAllNotificationsRead, onSuccess: refresh, onError: (e) => toastError(e) })
  const remove = useMutation({
    mutationFn: (ids: string[] | null) => ids ? api.deleteNotifications(ids) : api.clearNotifications(),
    onSuccess: () => {
      stopSelecting()
      setConfirm(null)
      refresh()
    },
    onError: (e) => {
      setConfirm(null)
      toastError(e)
    },
  })
  const items = (inbox.data?.items ?? []).filter((n) => filter === "all" || !n.read_at)
  const unread = inbox.data?.unread ?? 0
  const ids = items.map((n) => n.id)
  const allSelected = ids.length > 0 && ids.every((id) => selected.has(id))
  const someSelected = selected.size > 0 && !allSelected

  const groups: { label: string; items: AppNotification[] }[] = []
  for (const n of items) {
    const label = dayGroup(n.created_at)
    const last = groups.at(-1)
    if (last?.label === label) last.items.push(n)
    else groups.push({ label, items: [n] })
  }

  function stopSelecting() {
    setSelecting(false)
    setSelected(new Set())
  }

  function startSelecting() {
    setSelecting(true)
    setSelected(new Set())
  }

  function changeFilter(next: "all" | "unread") {
    setFilter(next)
    stopSelecting()
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(ids))
  }

  const open = async (n: AppNotification) => {
    if (!n.read_at) {
      await api.markNotificationRead(n.id).catch(() => undefined)
      refresh()
    }
    if (n.link) navigate(n.link)
  }

  return (
    <div className="bl-enter min-w-0 max-w-3xl mx-auto space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segmented
          label="Show"
          value={filter}
          onChange={changeFilter}
          options={[{ value: "all", label: "All" }, { value: "unread", label: "Unread", count: unread }]}
        />
        {selecting ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="flex h-7 items-center gap-2 px-1.5 text-footnote text-ink-secondary">
              <Checkbox
                checked={someSelected ? "indeterminate" : allSelected}
                onCheckedChange={toggleAll}
                onClick={(event) => event.stopPropagation()}
                aria-label="Select all notifications"
              />
              <span className="cursor-pointer select-none" onClick={toggleAll}>
                {selected.size ? `${selected.size} selected` : "Select all"}
              </span>
            </span>
            <Button size="sm" variant="quiet" icon={<Trash2 />} disabled={!selected.size || remove.isPending} onClick={() => setConfirm("selected")}>
              <span className="max-sm:sr-only">Delete</span>
            </Button>
            <Button size="sm" variant="quiet" onClick={stopSelecting}>Done</Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-1">
            {unread ? <Button size="sm" variant="quiet" icon={<CheckCheck />} disabled={readAll.isPending} onClick={() => readAll.mutate()}><span className="max-sm:sr-only">Mark all read</span></Button> : null}
            <Button size="sm" variant="quiet" icon={<ListChecks />} disabled={!items.length} onClick={startSelecting}><span className="max-sm:sr-only">Select</span></Button>
            <Button size="sm" variant="quiet" icon={<Settings />} onClick={() => navigate("/settings/notifications")}><span className="max-sm:sr-only">Settings</span></Button>
            <Button size="sm" variant="quiet" icon={<Trash2 />} disabled={!inbox.data?.items.length || remove.isPending} onClick={() => setConfirm("all")}><span className="max-sm:sr-only">Clear all</span></Button>
          </div>
        )}
      </div>
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
                {group.items.map((n, i) => (
                  <NotificationRow
                    key={n.id}
                    n={n}
                    index={i}
                    selecting={selecting}
                    selected={selected.has(n.id)}
                    onOpen={() => void open(n)}
                    onToggle={() => toggle(n.id)}
                    onChange={refresh}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      <AlertDialog open={confirm !== null} onOpenChange={(next) => { if (!next) setConfirm(null) }}>
        <AlertDialogContent className="max-w-sm">
          <DialogHeader>
            <AlertDialogTitle className="type-title-3">
              {confirm === "all" ? "Clear all notifications?" : `Delete ${selected.size} notification${selected.size === 1 ? "" : "s"}?`}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-callout text-ink-secondary">
              They leave your inbox for good. Nothing else is deleted.
            </AlertDialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-5">
            <Button variant="quiet" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate(confirm === "all" ? null : [...selected])}
            >
              {confirm === "all" ? "Clear all" : "Delete"}
            </Button>
          </DialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function NotificationRow({ n, index, selecting, selected, onOpen, onToggle, onChange }: {
  n: AppNotification
  index: number
  selecting: boolean
  selected: boolean
  onOpen: () => void
  onToggle: () => void
  onChange: () => void
}) {
  const kind = KIND[n.kind] ?? { icon: Bell, tile: "bg-surface-sunk text-ink-secondary" }
  const unread = !n.read_at
  const actions: MenuAction[] = [
    ...(unread ? [{ label: "Mark read", icon: <CheckCheck />, onSelect: () => void api.markNotificationRead(n.id).then(onChange) }] : []),
    { label: "Delete", icon: <Trash2 />, danger: true, onSelect: () => void api.deleteNotification(n.id).then(onChange).catch((e) => toastError(e)) },
  ]
  const content = (
    <>
      <span className="flex items-center gap-2">
        <span className={cn("truncate text-callout", unread ? "font-semibold text-ink" : "text-ink-secondary")}>{n.title}</span>
        {unread ? <span className="size-2 shrink-0 rounded-full bg-sun" role="img" aria-label="Unread" /> : null}
      </span>
      {n.body ? <span className="mt-0.5 line-clamp-2 block text-footnote text-ink-secondary">{n.body}</span> : null}
      <span className="mt-0.5 block text-caption font-medium text-ink-tertiary">{formatAgo(n.created_at)}</span>
    </>
  )
  const row = (
    <li
      style={{ "--i": index } as React.CSSProperties}
      onClick={selecting ? onToggle : undefined}
      className={cn(
        "bl-enter relative grid grid-cols-[36px_minmax(0,1fr)_auto] items-start gap-3 border-t border-separator px-4 py-3 first:border-t-0 hover:bg-highlight",
        selecting && "cursor-pointer select-none",
        selected && "bg-highlight",
      )}
    >
      <span className={cn("grid size-9 place-items-center rounded-full", kind.tile)}>
        <kind.icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
      </span>
      {selecting ? (
        <span className="min-w-0 text-left">{content}</span>
      ) : (
        <button type="button" onClick={onOpen} className="min-w-0 cursor-pointer text-left after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-focus">
          {content}
        </button>
      )}
      {selecting ? (
        <Checkbox
          checked={selected}
          onCheckedChange={onToggle}
          onClick={(event) => event.stopPropagation()}
          aria-label={`Select ${n.title}`}
          className="mt-1.5"
        />
      ) : (
        <ActionMenuButton actions={actions} label={`More for ${n.title}`} className="relative z-10 -my-1" />
      )}
    </li>
  )
  return selecting ? row : <ActionContextMenu actions={actions}>{row}</ActionContextMenu>
}

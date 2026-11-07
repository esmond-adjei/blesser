import { RowMenu } from "../ui/row-menu"
import { MenuItem } from "../ui/menu"
import { SIDEBAR_NAV } from "./Sidebar"
import { FlaskConical } from "lucide-react"
import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Bell, CalendarCheck2, Loader2, Settings, Trash2 } from "lucide-react"
import * as api from "../../lib/api"
import { formatRelativeDate } from "../../lib/format"
import { browserTimezone } from "../../lib/push"
import { useNotificationInbox } from "../../lib/queries"
import { toastSuccess } from "../../lib/toast"
import { cn } from "../../lib/utils"
import { Skeleton } from "../ui/feedback"
import { Popover } from "../ui/popover"
import { useSettingsParam } from "../dialogs/SettingsDialog"

/** Also reports the browser's timezone once, so deadline reminders count days in the person's own calendar. */
export function NotificationBell() {
  const { data, isLoading } = useNotificationInbox()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [, setSettings] = useSettingsParam()
  const reportedZone = React.useRef(false)

  React.useEffect(() => {
    if (!data || data.timezone || reportedZone.current) return
    const zone = browserTimezone()
    if (!zone) return
    reportedZone.current = true
    api.updateNotificationPreferences({ timezone: zone }).catch(() => {
      /* UTC until the next load: harmless */
    })
  }, [data])

  const unread = data?.unread ?? 0
  const items = data?.items ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] })

  async function open(item: api.AppNotification, close: () => void) {
    close()
    if (!item.read_at) {
      await api.markNotificationRead(item.id).catch(() => undefined)
      void refresh()
    }
    if (item.link) navigate(item.link)
  }

  const markAll = useMutation({
    mutationFn: api.markAllNotificationsRead,
    onSuccess: refresh,
  })
  const remove = useMutation({
    mutationFn: (id: string | null) => id === null ? api.clearNotifications() : api.deleteNotification(id),
    onSuccess: async (_, id) => {
      await refresh()
      toastSuccess(id === null ? "All notifications cleared" : "Notification deleted")
    },
  })
  const busy = markAll.isPending || remove.isPending
  const actionError = remove.error ?? markAll.error

  return (
    <Popover
      label="Notifications"
      align="end"
      className="sm:w-96 overflow-hidden p-0"
      trigger={(props) => (
        <button
          type="button"
          {...props}
          data-tooltip="Notifications"
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
          className="relative flex size-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Bell className="size-4" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-xs font-semibold leading-none text-primary-foreground">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
      )}
    >
      {(close) => (
        <div>
          <div className="flex items-center justify-between px-2 py-1.5 border-b border-border">
            <p className="text-sm font-medium">Notifications</p>
            <div className="flex items-center gap-1">
              <button
                type="button"
                data-tooltip="Notification settings"
                aria-label="Notification settings"
                onClick={() => {
                  close()
                  setSettings("notifications")
                }}
                className="flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              >
                <Settings className="size-3.5" />
              </button>
            </div>
          </div>

          {actionError && (
            <p role="alert" className="border-b border-border bg-destructive/5 px-3 py-2 text-xs text-destructive">
              {api.apiMessage(actionError)}
            </p>
          )}
          <div aria-busy={busy} className="nice-scroll max-h-96 overflow-y-auto p-2">
            {isLoading ? (
              <div aria-label="Loading notifications" aria-busy="true" className="space-y-2 p-1">
                {Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-10" />)}
              </div>
            ) : items.length === 0 ? (
              <p className="px-2 pb-3 pt-1 text-xs text-muted-foreground">
                Nothing yet. Finished runs, ready drafts and coming deadlines show up here.
              </p>
            ) : (
              <ul className="space-y-0.5">
                {items.map((item) => (
                  <li key={item.id} className="group relative flex items-start gap-1 rounded-md hover:bg-accent/50">
                    <button
                      type="button"
                      onClick={() => open(item, close)}
                      disabled={busy}
                      className="flex min-w-0 flex-1 cursor-pointer items-start gap-2 rounded-md pl-2 pr-9 py-2 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
                    >
                      <NotificationIcon link={item.link} unread={!item.read_at} />
                      <span className="min-w-0 flex-1">
                        <span className={cn("block text-sm", !item.read_at && "font-medium")}>{item.title}</span>
                        {item.body && <span className="mt-0.5 block text-xs text-muted-foreground">{item.body}</span>}
                        <span className="mt-0.5 ml-auto block text-xs text-muted-foreground">
                          <CalendarCheck2 className="size-3 mr-1 inline" />
                          {formatRelativeDate(item.created_at)}
                          {!item.read_at && <span className="sr-only"> (unread)</span>}
                        </span>
                      </span>
                    </button>
                    <RowMenu variant="sidebar" label={`Actions for ${item.title}`}>
                      <MenuItem disabled={busy} onSelect={() => remove.mutate(item.id)} destructive><Trash2 className="size-3.5" />Delete notification</MenuItem>
                    </RowMenu>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {items.length > 0 && (
            <div className="flex items-center justify-between gap-3 border-t border-border px-3 py-2">
              <button
                type="button"
                onClick={() => markAll.mutate()}
                disabled={busy || unread === 0}
                className="cursor-pointer rounded px-1 py-1 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-default disabled:opacity-50"
              >
                {markAll.isPending ? "Marking as read..." : "Mark all read"}
              </button>
              <button
                type="button"
                onClick={() => remove.mutate(null)}
                disabled={busy}
                data-tooltip="Delete all notifications, including older ones"
                className="flex cursor-pointer items-center gap-1.5 rounded px-1 py-1 text-xs text-muted-foreground hover:text-destructive focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-wait disabled:opacity-50"
              >
                {remove.isPending && remove.variables === null
                  ? <Loader2 className="size-3.5 animate-spin" />
                  : <Trash2 className="size-3.5" />}
                {remove.isPending && remove.variables === null ? "Clearing..." : "Clear all"}
              </button>
            </div>
          )}
        </div>
      )}
    </Popover>
  )
}

function NotificationIcon({ link, unread }: { link: string; unread: boolean }) {
  const Icon = SIDEBAR_NAV.find(item => link.startsWith(item.to))?.icon ?? (link.startsWith("/runs/") ? FlaskConical : Bell)
  return <span className="relative mt-0.5 shrink-0"><Icon className="size-4 text-muted-foreground" />{unread && <span className="absolute -right-1 -top-1 size-1.5 rounded-full bg-primary" />}</span>
}

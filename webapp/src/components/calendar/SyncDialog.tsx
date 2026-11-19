import * as React from "react"
import { Copy, RefreshCw } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { Button, Input, buttonVariants } from "@blesser/ui"
import * as api from "../../lib/api"
import { useCalendarFeed } from "../../lib/opportunities"
import { toastError, toastSuccess } from "../../lib/toast"
import { ErrorState } from "../feedback/EmptyState"
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog"

export function SyncDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      {open ? (
        <DialogContent className="max-w-lg" onClose={onClose}>
          <DialogHeader>
            <DialogTitle>Sync with your calendar</DialogTitle>
            <DialogDescription>
              Subscribe once and your application deadlines and dated to-dos appear in your calendar and stay up to date. The link is private: anyone with it can see your deadlines.
            </DialogDescription>
          </DialogHeader>
          <DialogBody><CalendarPanel /></DialogBody>
        </DialogContent>
      ) : null}
    </Dialog>
  )
}

function CalendarPanel() {
  const [enabled, setEnabled] = React.useState(false)
  const feed = useCalendarFeed(enabled)
  const client = useQueryClient()
  const [rotating, setRotating] = React.useState(false)
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toastSuccess("Link copied")
    } catch (err) {
      toastError(err, "Couldn't copy")
    }
  }
  return (
    <div className="space-y-3">
      {!enabled ? (
        <Button size="sm" variant="secondary" onClick={() => setEnabled(true)}>
          Get my calendar link
        </Button>
      ) : feed.isLoading ? (
        <div className="h-10 animate-pulse rounded-md bg-surface-sunk motion-reduce:animate-none" />
      ) : feed.data ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Input readOnly value={feed.data.url} aria-label="Calendar subscription link" className="h-control-sm min-w-[240px] flex-1 type-code" onFocus={(e) => e.currentTarget.select()} />
            <Button size="sm" onClick={() => void copy(feed.data.url)} icon={<Copy />}>
              Copy
            </Button>
            <a href={feed.data.webcal_url} className={buttonVariants({ size: "sm", variant: "secondary" })}>
              Open in calendar app
            </a>
          </div>
          <ul className="list-disc space-y-1 pl-5 text-footnote text-ink-secondary">
            <li>Google Calendar: Other calendars, then From URL, and paste the link.</li>
            <li>Apple Calendar: File, then New Calendar Subscription.</li>
            <li>Outlook: Add calendar, then Subscribe from web.</li>
          </ul>
          <Button
            size="sm"
            variant="quiet"
            disabled={rotating}
            onClick={async () => {
              setRotating(true)
              try {
                const next = await api.rotateCalendarFeed()
                client.setQueryData(["calendar-feed"], next)
                toastSuccess("New link made. The old one no longer works.")
              } catch (err) {
                toastError(err, "Couldn't make a new link")
              } finally {
                setRotating(false)
              }
            }}
            icon={<RefreshCw />}
          >
            Make a new link
          </Button>
        </div>
      ) : (
        <ErrorState compact title="Your calendar link didn't load" description="Try again in a moment." onRetry={() => void feed.refetch()} />
      )}
    </div>
  )
}

import { Link } from "react-router-dom"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2, Pause, Play, Trash2 } from "lucide-react"
import { Button } from "@blesser/ui"
import * as api from "../../lib/api"
import { CATEGORY_LABELS } from "../../lib/opportunities"
import { SCHEDULES_KEY, useSchedules } from "../../lib/schedules"
import { runSummary, scheduleStatus, siteLabel } from "../../lib/scanLog"
import { toastError } from "../../lib/toast"
import type { ScanSchedule } from "../../lib/types"
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"

export function SchedulesDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient()
  const schedules = useSchedules(open)
  const refresh = () => {
    void client.invalidateQueries({ queryKey: SCHEDULES_KEY })
    void client.invalidateQueries({ queryKey: ["scans"] })
  }
  const data = schedules.data
  const rows = data?.schedules ?? []
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Weekly scans</DialogTitle>
          <p className="text-callout text-ink-secondary">
            Scans that run again every week, so you hear about new opportunities without starting them yourself. You get a notification only when a run finds something new.
          </p>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-3 pb-2">
          {schedules.isLoading ? (
            <p className="flex items-center gap-2 text-footnote text-ink-secondary"><Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" /> Loading</p>
          ) : schedules.isError ? (
            <p className="text-footnote text-ink-secondary">Your weekly scans didn't load. Try again in a moment.</p>
          ) : rows.length ? (
            <ul aria-label="Your weekly scans">
              {rows.map((row) => <ScheduleRow key={row.id} schedule={row} onChanged={refresh} />)}
            </ul>
          ) : (
            <p className="text-footnote text-ink-secondary">None yet. Open a scan and choose Repeat weekly, or turn on Weekly before you start one.</p>
          )}
          {data ? (
            <p className="text-caption text-ink-tertiary">{rows.length} of {data.max_schedules} weekly scans</p>
          ) : null}
        </DialogBody>
        <DialogFooter className="pt-3">
          <Button variant="quiet" onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function scheduleTitle(schedule: ScanSchedule): string {
  const who = schedule.categories.map((c) => CATEGORY_LABELS[c] ?? c).join(", ")
  return schedule.region ? `${who} in ${schedule.region}` : who
}

function ScheduleRow({ schedule, onChanged }: { schedule: ScanSchedule; onChanged: () => void }) {
  const title = scheduleTitle(schedule)
  const toggle = useMutation({
    mutationFn: () => api.updateSchedule(schedule.id, { paused: !schedule.paused }),
    onSuccess: onChanged,
    onError: (err) => toastError(err),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteSchedule(schedule.id),
    onSuccess: onChanged,
    onError: (err) => toastError(err),
  })
  const last = schedule.last_run
  return (
    <li className="flex items-start gap-3 border-t border-separator py-2.5 first:border-t-0">
      <div className="min-w-0 flex-1">
        <p className="truncate text-callout font-semibold text-ink">{title}</p>
        {schedule.focus ? <p className="truncate text-footnote text-ink-secondary" title={schedule.focus}>{schedule.focus}</p> : null}
        {schedule.sites.length ? (
          <p className="truncate text-footnote text-ink-secondary">Reads {schedule.sites.map(siteLabel).join(", ")}</p>
        ) : null}
        <p className="text-caption text-ink-tertiary">
          {scheduleStatus(schedule)}
          {last ? (
            <>
              {". "}
              <Link to={`/scans/${last.scan_id}`} className="text-link hover:underline">
                Last run: {last.status === "running" ? "running now" : runSummary(last)}
              </Link>
            </>
          ) : null}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          size="sm"
          variant="quiet"
          iconOnly
          aria-label={schedule.paused ? `Resume ${title}` : `Pause ${title}`}
          title={schedule.paused ? "Resume" : "Pause"}
          icon={schedule.paused ? <Play /> : <Pause />}
          disabled={toggle.isPending}
          onClick={() => toggle.mutate()}
        />
        <Button
          size="sm"
          variant="quiet"
          iconOnly
          aria-label={`Stop repeating ${title}`}
          title="Stop repeating"
          icon={<Trash2 />}
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        />
      </div>
    </li>
  )
}

import { Checkbox } from "../components/ui/checkbox"
import * as React from "react"
import { Link } from "react-router-dom"
import { ArrowUpRight, Plus, Trash2 } from "lucide-react"
import { OPEN_STATUSES, STATUSES, STATUS_LABEL, useApplicationMutations, useApplications } from "../lib/applications"
import { toastError, toastSuccess } from "../lib/toast"
import type { Application, ApplicationStatus as Status, RequirementItem } from "../lib/types"
import {
  APPLICATION_STAGES,
  ApplicationStatus,
  Button,
  Countdown,
  Field,
  Input,
  Select,
  Textarea,
  buttonVariants,
  cn,
  daysUntil,
  type ApplicationStage,
} from "@blesser/ui"
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog"
import { EmptyState, ErrorState } from "../components/feedback/EmptyState"
import { PageHeader, Segmented } from "../components/layout/PageHeader"
import trackedArt from "@blesser/ui/illustrations/spot-empty-tracked.webp"

const stage = (status: Status): ApplicationStage => (status === "rejected" ? "not-this-time" : status)

function Deadline({ app }: { app: Application }) {
  if (!OPEN_STATUSES.includes(app.status) && app.status !== "submitted") return null
  if (!app.deadline_date) return app.deadline ? <Countdown variant="text" label={app.deadline} /> : null
  return <Countdown variant="text" daysLeft={daysUntil(app.deadline_date)} date={app.deadline_date} />
}

/** Five quiet steps; the full stepper lives in the dialog. */
function StageDots({ status }: { status: Status }) {
  const index = APPLICATION_STAGES.findIndex((s) => s.id === status)
  const ended = status === "rejected"
  return (
    <span className="hidden items-center gap-1 md:flex" aria-hidden="true">
      {APPLICATION_STAGES.map((s, i) => (
        <span
          key={s.id}
          className={cn("h-1 w-3 rounded-full", !ended && i <= index ? (status === "accepted" ? "bg-bloom" : "bg-forest") : "bg-separator")}
        />
      ))}
    </span>
  )
}

const FILTERS = [
  { value: "active", label: "In progress" },
  { value: "all", label: "All" },
  ...STATUSES,
]

export function Applications() {
  const { data, isLoading, isError, refetch } = useApplications()
  const { update } = useApplicationMutations()
  const [filter, setFilter] = React.useState("active")
  const [editing, setEditing] = React.useState<Application | null>(null)
  const [adding, setAdding] = React.useState(false)

  const apps = (data ?? []).filter((a) => {
    if (filter === "all") return true
    if (filter === "active") return a.status !== "accepted" && a.status !== "rejected"
    return a.status === filter
  })

  const countFor = (value: string) =>
    value === "all"
      ? data?.length
      : value === "active"
        ? data?.filter((a) => a.status !== "accepted" && a.status !== "rejected").length
        : data?.filter((a) => a.status === value).length

  return (
    <div className="space-y-5">
      <PageHeader
        title="Applications"
        description="Everything you're applying for. Saved and preparing applications get reminders 14, 7 and 1 days before the deadline."
        actions={
          <Button size="sm" onClick={() => setAdding(true)} icon={<Plus />}>
            Add by hand
          </Button>
        }
      />

      <Segmented
        label="Filter by status"
        value={filter}
        onChange={setFilter}
        options={FILTERS.map((f) => ({ value: f.value, label: f.label, count: countFor(f.value) || undefined }))}
      />

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
      ) : isError ? (
        <ErrorState title="Your applications didn't load" description="Try again in a moment." onRetry={() => void refetch()} />
      ) : apps.length === 0 ? (
        <EmptyState
          illustration={trackedArt}
          title={data?.length ? "Nothing with this status" : "Nothing tracked yet"}
          description="Track an opportunity from the catalogue, or add one by hand."
          action={
            <Link to="/opportunities" className={buttonVariants({ size: "sm" })}>
              Browse opportunities
            </Link>
          }
        />
      ) : (
        <ul className="divide-y divide-separator rounded-lg border border-separator bg-surface">
          {apps.map((app) => {
            const done = app.requirements.filter((r) => r.done).length
            const meta = [app.organization, app.kind, app.requirements.length ? `${done} of ${app.requirements.length} ready` : ""].filter(Boolean)
            return (
              <li key={app.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
                <button type="button" className="min-w-0 flex-1 cursor-pointer text-left" onClick={() => setEditing(app)}>
                  <span className="block text-callout font-semibold text-ink hover:underline">{app.title}</span>
                  <span className="mt-0.5 block truncate text-footnote text-ink-tertiary">{meta.join(" · ")}</span>
                </button>
                <div className="flex shrink-0 items-center gap-3">
                  <StageDots status={app.status} />
                  <Select
                    aria-label={`Status of ${app.title}`}
                    className="h-control-sm w-[140px] pr-8 text-footnote"
                    value={app.status}
                    onChange={(e) =>
                      update.mutate(
                        { id: app.id, body: { status: e.target.value as Status } },
                        { onError: (err) => toastError(err, "The status didn't save. Try again.") },
                      )
                    }
                  >
                    {STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </Select>
                  <span className="ml-auto w-24 text-right sm:ml-0">
                    <Deadline app={app} />
                  </span>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <ApplicationDialog app={editing} onClose={() => setEditing(null)} />
      <AddDialog open={adding} onClose={() => setAdding(false)} />
    </div>
  )
}

function ApplicationDialog({ app, onClose }: { app: Application | null; onClose: () => void }) {
  const { update, remove } = useApplicationMutations()
  const [shown, setShown] = React.useState<Application | null>(app)
  const [notes, setNotes] = React.useState("")
  const [deadline, setDeadline] = React.useState("")
  const [requirements, setRequirements] = React.useState<RequirementItem[]>([])
  const [newItem, setNewItem] = React.useState("")
  if (app && app !== shown) {
    setShown(app)
    setNotes(app.notes)
    setDeadline(app.deadline_date ?? "")
    setRequirements(app.requirements)
    setNewItem("")
  }
  const save = (body: Parameters<typeof update.mutate>[0]["body"]) =>
    shown && update.mutate({ id: shown.id, body }, { onError: (err) => toastError(err, "Couldn't save") })

  return (
    <Dialog open={!!app} onOpenChange={(open) => !open && onClose()}>
      {shown ? (
        <DialogContent className="max-w-xl" onClose={onClose}>
          <DialogHeader>
            <DialogTitle>{shown.title}</DialogTitle>
            <DialogDescription>
              {[shown.organization, shown.kind, STATUS_LABEL[shown.status]].filter(Boolean).join(" · ")}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <ApplicationStatus status={stage(shown.status)} />
            {shown.benefits ? <p className="text-callout font-semibold text-ink">{shown.benefits}</p> : null}
            <Field label="Deadline">
              <Input
                type="date"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                onBlur={() => deadline !== (shown.deadline_date ?? "") && save({ deadline_date: deadline || null })}
              />
            </Field>
            <div>
              <p className="mb-1.5 text-headline text-ink">What to prepare</p>
              <ul className="space-y-1.5">
                {requirements.map((r, i) => (
                  <li key={`${r.label}-${i}`} className="flex items-center gap-2 text-callout">
                    <Checkbox
                      checked={r.done}
                      aria-label={r.label}
                      onCheckedChange={() => {
                        const next = requirements.map((x, j) => (j === i ? { ...x, done: !x.done } : x))
                        setRequirements(next)
                        save({ requirements: next })
                      }}
                    />
                    <span className={cn(r.done && "text-ink-tertiary line-through")}>{r.label}</span>
                  </li>
                ))}
              </ul>
              <form
                className="mt-2 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (!newItem.trim()) return
                  const next = [...requirements, { label: newItem.trim(), done: false }]
                  setRequirements(next)
                  setNewItem("")
                  save({ requirements: next })
                }}
              >
                <Input
                  aria-label="Add an item"
                  placeholder="Add an item, e.g. Two references"
                  value={newItem}
                  onChange={(e) => setNewItem(e.target.value)}
                  className="flex-1"
                />
                <Button type="submit" size="sm" variant="secondary" disabled={!newItem.trim()}>
                  Add
                </Button>
              </form>
            </div>
            <Field label="Notes">
              <Textarea
                rows={4}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={() => notes !== shown.notes && save({ notes })}
              />
            </Field>
          </DialogBody>
          <DialogFooter className="flex-wrap">
            <Button
              size="sm"
              variant="quiet"
              className="mr-auto text-critical hover:bg-critical-soft"
              onClick={() =>
                remove.mutate(shown.id, {
                  onSuccess: () => {
                    toastSuccess("Removed from your applications")
                    onClose()
                  },
                  onError: (err) => toastError(err, "Couldn't remove it"),
                })
              }
              icon={<Trash2 />}
            >
              Remove
            </Button>
            {shown.link ? (
              <a href={shown.link} target="_blank" rel="noopener noreferrer" className={buttonVariants({ size: "sm", variant: "secondary" })}>
                Open <ArrowUpRight />
              </a>
            ) : null}
            <Button size="sm" variant="primary" onClick={onClose}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      ) : null}
    </Dialog>
  )
}

function AddDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { create } = useApplicationMutations()
  const [form, setForm] = React.useState({ title: "", organization: "", link: "", deadline: "" })
  const set = (key: keyof typeof form, value: string) => setForm((f) => ({ ...f, [key]: value }))
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" onClose={onClose}>
        <form
          className="flex min-h-0 flex-auto flex-col"
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              { title: form.title.trim(), organization: form.organization.trim(), link: form.link.trim(), deadline: form.deadline },
              {
                onSuccess: () => {
                  setForm({ title: "", organization: "", link: "", deadline: "" })
                  onClose()
                },
                onError: (err) => toastError(err, "Couldn't add it"),
              },
            )
          }}
        >
          <DialogHeader>
            <DialogTitle>Add an application</DialogTitle>
            <DialogDescription>For something that isn't in the catalogue.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <Field label="Name">
              <Input value={form.title} onChange={(e) => set("title", e.target.value)} required maxLength={300} />
            </Field>
            <Field label="Organization">
              <Input value={form.organization} onChange={(e) => set("organization", e.target.value)} maxLength={200} />
            </Field>
            <Field label="Link">
              <Input type="url" value={form.link} onChange={(e) => set("link", e.target.value)} placeholder="https://" />
            </Field>
            <Field label="Deadline">
              <Input type="date" value={form.deadline} onChange={(e) => set("deadline", e.target.value)} />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="quiet" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={create.isPending || !form.title.trim()}>
              Add
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

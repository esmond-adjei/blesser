import * as React from "react"
import { Link } from "react-router-dom"
import { ArrowUpRight, Plus, Trash2 } from "lucide-react"
import { OPEN_STATUSES, STATUSES, STATUS_LABEL, useApplicationMutations, useApplications } from "../lib/applications"
import { toastError, toastSuccess } from "../lib/toast"
import type { Application, ApplicationStatus as Status, RequirementItem } from "../lib/types"
import {
  ApplicationStatus,
  Button,
  Chip,
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

const stage = (status: Status): ApplicationStage => (status === "rejected" ? "not-this-time" : status)

function Deadline({ app }: { app: Application }) {
  if (!OPEN_STATUSES.includes(app.status) && app.status !== "submitted") return null
  if (!app.deadline_date) return app.deadline ? <Countdown label={app.deadline} /> : null
  return <Countdown daysLeft={daysUntil(app.deadline_date)} date={app.deadline_date} />
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

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="type-title-2">Applications</h1>
          <p className="text-callout text-ink-secondary max-w-2xl">
            Everything you're applying for, from saved to accepted. Saved and preparing applications get deadline
            reminders 14, 7 and 1 days before.
          </p>
        </div>
        <Button size="sm" onClick={() => setAdding(true)} icon={<Plus />}>
          Add by hand
        </Button>
      </header>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {FILTERS.map((f) => {
          const count =
            f.value === "all"
              ? data?.length
              : f.value === "active"
                ? data?.filter((a) => a.status !== "accepted" && a.status !== "rejected").length
                : data?.filter((a) => a.status === f.value).length
          return (
            <Chip key={f.value} selected={filter === f.value} onClick={() => setFilter(f.value)}>
              {f.label}
              {count ? <span className="tabular-nums opacity-70">{count}</span> : null}
            </Chip>
          )
        })}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState title="Your applications didn't load" description="Try again in a moment." onRetry={() => void refetch()} />
      ) : apps.length === 0 ? (
        <EmptyState
          title={data?.length ? "Nothing with this status" : "Nothing tracked yet"}
          description="Track an opportunity from the catalogue, or add one by hand."
          action={
            <Link to="/opportunities" className={buttonVariants({ variant: "primary" })}>
              Browse opportunities
            </Link>
          }
        />
      ) : (
        <ul className="grid gap-4">
          {apps.map((app) => {
            const done = app.requirements.filter((r) => r.done).length
            return (
              <li key={app.id} className="flex flex-col gap-4 rounded-lg border border-separator bg-surface p-5 shadow-elevation-1">
                <div className="flex flex-wrap items-start gap-3">
                  <button type="button" className="min-w-0 flex-1 basis-60 cursor-pointer text-left" onClick={() => setEditing(app)}>
                    <span className="block text-title-3 text-ink hover:underline">{app.title}</span>
                    <span className="mt-0.5 block text-callout text-ink-secondary">
                      {[app.organization, app.kind].filter(Boolean).join(" · ")}
                      {app.requirements.length ? ` · ${done} of ${app.requirements.length} ready` : ""}
                    </span>
                  </button>
                  <Deadline app={app} />
                </div>
                <div className="flex flex-wrap items-end gap-4">
                  <ApplicationStatus status={stage(app.status)} className="min-w-0 flex-1 basis-60" />
                  <Select
                    aria-label={`Status of ${app.title}`}
                    className="h-control-sm w-auto min-w-[150px] text-callout"
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
                    <input
                      type="checkbox"
                      className="size-4 accent-forest"
                      checked={r.done}
                      aria-label={r.label}
                      onChange={() => {
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

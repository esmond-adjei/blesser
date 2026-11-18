import { Checkbox } from "../components/ui/checkbox"
import * as React from "react"
import { Link } from "react-router-dom"
import { ArrowUpRight, CalendarDays, Columns3, List, MoveRight, PanelRightOpen, Plus, Trash2 } from "lucide-react"
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
  Textarea,
  buttonVariants,
  cn,
  daysUntil,
  type ApplicationStage,
  type ChipTone,
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
import { DeadlineCalendar } from "../components/applications/DeadlineCalendar"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../components/ui/menu"

const stage = (status: Status): ApplicationStage => (status === "rejected" ? "not-this-time" : status)

const STATUS_TONE: Record<Status, ChipTone> = {
  saved: "neutral",
  preparing: "sun",
  submitted: "info",
  interview: "forest",
  accepted: "bloom",
  rejected: "neutral",
}

const COLUMNS: { id: string; label: string; statuses: Status[]; dot: string }[] = [
  { id: "saved", label: "Saved", statuses: ["saved"], dot: "bg-control-border" },
  { id: "preparing", label: "Preparing", statuses: ["preparing"], dot: "bg-sun" },
  { id: "submitted", label: "Submitted", statuses: ["submitted"], dot: "bg-info" },
  { id: "interview", label: "Interview", statuses: ["interview"], dot: "bg-forest" },
  { id: "decision", label: "Decision", statuses: ["accepted", "rejected"], dot: "bg-bloom" },
]

function Deadline({ app, className }: { app: Application; className?: string }) {
  if (!OPEN_STATUSES.includes(app.status) && app.status !== "submitted") return null
  if (!app.deadline_date) return app.deadline ? <Countdown variant="text" label={app.deadline} className={className} /> : null
  return <Countdown variant="text" daysLeft={daysUntil(app.deadline_date)} date={app.deadline_date} className={className} />
}

const FILTERS = [
  { value: "active", label: "In progress" },
  { value: "all", label: "All" },
  ...STATUSES,
]

type View = "list" | "board" | "calendar"
const VIEW_KEY = "blesser.applications.view"

function useView(): [View, (view: View) => void] {
  const [view, setView] = React.useState<View>(() => {
    try {
      const saved = localStorage.getItem(VIEW_KEY)
      return saved === "board" || saved === "calendar" ? saved : "list"
    } catch {
      return "list"
    }
  })
  return [
    view,
    (next) => {
      setView(next)
      try {
        localStorage.setItem(VIEW_KEY, next)
      } catch {
        // Storage can be blocked; the choice still holds for this visit.
      }
    },
  ]
}

function useAppActions(onOpen: (app: Application) => void) {
  const { update, remove } = useApplicationMutations()
  const move = (app: Application, status: Status) =>
    app.status !== status &&
    update.mutate({ id: app.id, body: { status } }, { onError: (err) => toastError(err, "The status didn't save. Try again.") })
  const actionsFor = (app: Application): MenuAction[] => [
    { label: "Open", icon: <PanelRightOpen />, onSelect: () => onOpen(app) },
    { kind: "radio", label: "Move to", icon: <MoveRight />, value: app.status, options: STATUSES, onChange: (v) => move(app, v as Status) },
    ...(app.link ? [{ label: "Official page", icon: <ArrowUpRight />, href: app.link } satisfies MenuAction] : []),
    { kind: "separator" },
    {
      label: "Remove",
      icon: <Trash2 />,
      danger: true,
      onSelect: () =>
        remove.mutate(app.id, {
          onSuccess: () => toastSuccess("Removed from your applications"),
          onError: (err) => toastError(err, "Couldn't remove it"),
        }),
    },
  ]
  return { move, actionsFor }
}

export function Applications() {
  const { data, isLoading, isError, refetch } = useApplications()
  const [filter, setFilter] = React.useState("active")
  const [view, setView] = useView()
  const [editing, setEditing] = React.useState<Application | null>(null)
  const [adding, setAdding] = React.useState(false)
  const { move, actionsFor } = useAppActions(setEditing)

  const apps = (data ?? []).filter((a) => {
    if (view !== "list" || filter === "all") return true
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

      <div className="flex flex-wrap items-center gap-2">
        {view === "list" ? (
          <Segmented
            label="Filter by status"
            value={filter}
            onChange={setFilter}
            className="min-w-0 flex-1 sm:flex-none"
            options={FILTERS.map((f) => ({ value: f.value, label: f.label, count: countFor(f.value) || undefined }))}
          />
        ) : null}
        <Segmented
          label="View"
          value={view}
          onChange={setView}
          className="ml-auto"
          options={[
            { value: "list", label: "List", icon: <List aria-hidden="true" /> },
            { value: "board", label: "Board", icon: <Columns3 aria-hidden="true" /> },
            { value: "calendar", label: "Calendar", icon: <CalendarDays aria-hidden="true" /> },
          ]}
        />
      </div>

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
      ) : isError ? (
        <ErrorState title="Your applications didn't load" description="Try again in a moment." onRetry={() => void refetch()} />
      ) : apps.length === 0 ? (
        <EmptyState
          title={data?.length ? "Nothing with this status" : "Nothing tracked yet"}
          description="Track an opportunity from the catalogue, or add one by hand."
          action={
            <Link to="/opportunities" className={buttonVariants({ size: "sm" })}>
              Browse opportunities
            </Link>
          }
        />
      ) : view === "calendar" ? (
        <DeadlineCalendar key="calendar" apps={apps} onOpen={setEditing} />
      ) : view === "board" ? (
        <Board key="board" apps={apps} onOpen={setEditing} onMove={move} actionsFor={actionsFor} />
      ) : (
        <ul key="list" className="divide-y divide-separator rounded-lg border border-separator bg-surface">
          {apps.map((app, i) => {
            const done = app.requirements.filter((r) => r.done).length
            const meta = [app.organization, app.requirements.length ? `${done} of ${app.requirements.length} ready` : ""].filter(Boolean)
            const actions = actionsFor(app)
            return (
              <ActionContextMenu key={app.id} actions={actions}>
                <li
                  style={{ "--i": i } as React.CSSProperties}
                  className="bl-enter flex items-center gap-3 px-3 py-3 transition-colors hover:bg-highlight/50 data-[state=open]:bg-highlight/50 sm:gap-4 sm:px-4"
                >
                  <button type="button" className="min-w-0 flex-1 cursor-pointer text-left" onClick={() => setEditing(app)}>
                    <span className="block text-callout font-semibold text-ink hover:underline">{app.title}</span>
                    {meta.length ? <span className="mt-0.5 block truncate text-footnote text-ink-tertiary">{meta.join(", ")}</span> : null}
                    <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 sm:hidden">
                      <Chip tone={STATUS_TONE[app.status]}>{STATUS_LABEL[app.status]}</Chip>
                      <Deadline app={app} />
                    </span>
                  </button>
                  <Chip tone={STATUS_TONE[app.status]} className="max-sm:hidden">
                    {STATUS_LABEL[app.status]}
                  </Chip>
                  <span className="w-24 justify-end text-right max-sm:hidden sm:flex">
                    <Deadline app={app} />
                  </span>
                  <ActionMenuButton actions={actions} label={`More for ${app.title}`} className="shrink-0" />
                </li>
              </ActionContextMenu>
            )
          })}
        </ul>
      )}

      <ApplicationDialog app={editing} onClose={() => setEditing(null)} />
      <AddDialog open={adding} onClose={() => setAdding(false)} />
    </div>
  )
}

const DRAG_TYPE = "application/x-blesser-application"

function Board({
  apps,
  onOpen,
  onMove,
  actionsFor,
}: {
  apps: Application[]
  onOpen: (app: Application) => void
  onMove: (app: Application, status: Status) => void
  actionsFor: (app: Application) => MenuAction[]
}) {
  const [dragging, setDragging] = React.useState<Application | null>(null)
  const [over, setOver] = React.useState<string | null>(null)
  const drop = (status: Status) => (e: React.DragEvent) => {
    e.preventDefault()
    const id = e.dataTransfer.getData(DRAG_TYPE)
    const app = apps.find((a) => a.id === id)
    if (app) onMove(app, status)
    setDragging(null)
    setOver(null)
  }
  const target = (key: string) => ({
    onDragOver: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes(DRAG_TYPE)) return
      e.preventDefault()
      e.dataTransfer.dropEffect = "move"
      if (over !== key) setOver(key)
    },
    onDragLeave: (e: React.DragEvent) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver((o) => (o === key ? null : o))
    },
  })

  return (
    <div className="nice-scroll -mx-4 overflow-x-auto px-4 pb-2 sm:-mx-8 sm:px-8">
      <div className="grid snap-x snap-mandatory auto-cols-[minmax(248px,85vw)] grid-flow-col gap-3 sm:auto-cols-[minmax(232px,1fr)]">
        {COLUMNS.map((col) => {
          const items = apps.filter((a) => col.statuses.includes(a.status))
          const decision = col.id === "decision"
          return (
            <section
              key={col.id}
              aria-label={col.label}
              {...(decision ? {} : { ...target(col.id), onDrop: drop(col.statuses[0]) })}
              className={cn(
                "flex min-h-64 snap-start flex-col gap-2 rounded-lg bg-surface-sunk p-2 transition-[box-shadow,background-color] duration-150",
                over === col.id && "bg-forest-soft/60 shadow-[inset_0_0_0_1.5px_var(--forest)]",
              )}
            >
              <h2 className="flex items-center gap-2 px-1.5 pt-1 pb-0.5 text-footnote font-semibold text-ink">
                <span aria-hidden="true" className={cn("size-2 rounded-full", col.dot)} />
                {col.label}
                <span className="ml-auto text-ink-tertiary tabular-nums">{items.length}</span>
              </h2>
              {decision && dragging ? (
                <div className="grid grid-cols-2 gap-2">
                  {(["accepted", "rejected"] as const).map((status) => (
                    <div
                      key={status}
                      {...target(status)}
                      onDrop={drop(status)}
                      className={cn(
                        "bl-enter grid h-16 place-items-center rounded-md border border-dashed border-input-border-hover text-center text-footnote text-ink-secondary transition-colors",
                        over === status && (status === "accepted" ? "border-bloom bg-bloom-soft text-bloom-ink" : "border-control-border bg-surface"),
                      )}
                    >
                      {STATUS_LABEL[status]}
                    </div>
                  ))}
                </div>
              ) : null}
              {items.map((app, i) => (
                <BoardTile
                  key={app.id}
                  app={app}
                  index={i}
                  actions={actionsFor(app)}
                  dragging={dragging?.id === app.id}
                  onOpen={() => onOpen(app)}
                  onDragStart={(e) => {
                    e.dataTransfer.setData(DRAG_TYPE, app.id)
                    e.dataTransfer.effectAllowed = "move"
                    setDragging(app)
                  }}
                  onDragEnd={() => {
                    setDragging(null)
                    setOver(null)
                  }}
                />
              ))}
              {items.length === 0 && !(decision && dragging) ? (
                <p className="grid flex-1 place-items-center rounded-md border border-dashed border-input-border px-3 py-6 text-center text-footnote text-ink-tertiary">
                  Drag an application here
                </p>
              ) : null}
            </section>
          )
        })}
      </div>
    </div>
  )
}

function BoardTile({
  app,
  index,
  actions,
  dragging,
  onOpen,
  onDragStart,
  onDragEnd,
}: {
  app: Application
  index: number
  actions: MenuAction[]
  dragging: boolean
  onOpen: () => void
  onDragStart: (e: React.DragEvent) => void
  onDragEnd: () => void
}) {
  const total = app.requirements.length
  const done = app.requirements.filter((r) => r.done).length
  const outcome = app.status === "accepted" || app.status === "rejected"
  return (
    <ActionContextMenu actions={actions}>
      <article
        draggable
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        style={{ "--i": index } as React.CSSProperties}
        className={cn(
          "bl-enter group flex cursor-grab flex-col gap-2 rounded-md bg-surface p-3 shadow-elevation-1 transition-[box-shadow,opacity,transform] duration-150 active:cursor-grabbing data-[state=open]:shadow-elevation-2",
          app.status === "accepted" && "bg-bloom-soft",
          dragging && "opacity-50",
        )}
      >
        <div className="flex items-start gap-1">
          <button type="button" onClick={onOpen} className="min-w-0 flex-1 cursor-pointer text-left">
            {app.organization ? <span className="block truncate text-caption text-ink-tertiary">{app.organization}</span> : null}
            <span className="line-clamp-2 text-callout font-semibold text-ink group-hover:underline">{app.title}</span>
          </button>
          <ActionMenuButton actions={actions} label={`More for ${app.title}`} className="-mt-1 -mr-1.5 size-7 shrink-0 opacity-100 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100" />
        </div>
        {outcome ? (
          <span className={cn("text-footnote", app.status === "accepted" ? "font-semibold text-bloom-ink" : "text-ink-secondary")}>
            {app.status === "accepted" ? "Accepted. Congratulations!" : "Not this time"}
          </span>
        ) : (
          <div className="flex items-center gap-3">
            <Deadline app={app} className="mr-auto" />
            {total ? (
              <span className="flex items-center gap-1.5 text-caption text-ink-tertiary tabular-nums" aria-label={`${done} of ${total} ready`}>
                <span aria-hidden="true" className="h-1 w-10 overflow-hidden rounded-full bg-surface-sunk">
                  <span className="block h-full rounded-full bg-forest transition-[width] duration-300" style={{ width: `${(100 * done) / total}%` }} />
                </span>
                {done}/{total}
              </span>
            ) : null}
          </div>
        )}
      </article>
    </ActionContextMenu>
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
              {[shown.organization, shown.kind].filter(Boolean).join(", ")}
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

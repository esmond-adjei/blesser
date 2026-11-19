import * as React from "react"
import { Link } from "react-router-dom"
import { Check, ChevronRight, Flag, Pencil, RotateCcw, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button, Field, Input, OpportunityArt, Select, Textarea, cn } from "@blesser/ui"
import { useIsMobile } from "../../hooks/use-mobile"
import { formatDay } from "../../lib/format"
import { useTodoMutations, useTodos } from "../../lib/opportunities"
import { toastError, toastSuccess } from "../../lib/toast"
import type { Todo, TodoPriority } from "../../lib/types"
import { EmptyState, ErrorState } from "../feedback/EmptyState"
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "../ui/shadcn/sheet"
import { TodoAdd, TodoRow, daysBetween, groupTodos, todayIso } from "../todos/TodoList"
import { parseIso, weekday } from "./dates"

const PRIORITIES: { value: TodoPriority; label: string }[] = [
  { value: "high", label: "High" },
  { value: "normal", label: "Normal" },
  { value: "low", label: "Low" },
]

function SideSheet({ open, onClose, children, label }: { open: boolean; onClose: () => void; children: React.ReactNode; label?: string }) {
  const phone = useIsMobile()
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent aria-label={label} side={phone ? "bottom" : "right"} className="gap-0 max-sm:max-h-[92dvh] sm:w-full sm:max-w-md">
        {children}
      </SheetContent>
    </Sheet>
  )
}

function dueText(date: string, today: string, done: boolean): { text: string; tone: string } {
  const text = `${weekday(parseIso(date))} ${formatDay(date)}`
  const d = daysBetween(today, date)
  if (done) return { text, tone: "text-ink" }
  if (d < 0) return { text: `${text}, overdue`, tone: "text-bloom-ink" }
  if (d === 0) return { text: `${text}, today`, tone: "text-sun-ink" }
  return { text, tone: "text-ink" }
}

/** One to-do's details and actions, opened from the calendar. */
export function TodoSheet({ todo, loading, onClose, onOpenApplication }: {
  todo: Todo | null
  loading: boolean
  onClose: () => void
  onOpenApplication: (id: string) => void
}) {
  const open = !!todo || loading
  const [shown, setShown] = React.useState<Todo | null>(null)
  if (todo && todo !== shown) setShown(todo)
  const current = todo ?? (open ? null : shown)
  const [editing, setEditing] = React.useState(false)
  const [editingId, setEditingId] = React.useState(current?.id)
  if (current?.id !== editingId) {
    setEditingId(current?.id)
    setEditing(false)
  }

  return (
    <SideSheet open={open} onClose={onClose}>
      {current ? (
        editing ? (
          <TodoEditForm key={current.id} todo={current} onDone={() => setEditing(false)} />
        ) : (
          <TodoDetail todo={current} onClose={onClose} onEdit={() => setEditing(true)} onOpenApplication={onOpenApplication} />
        )
      ) : (
        <SheetHeader className="p-5 pr-14">
          <SheetTitle className="sr-only">To-do</SheetTitle>
          <SheetDescription className="sr-only">Loading the to-do</SheetDescription>
          <div role="status" aria-label="Loading the to-do" className="space-y-3">
            <div className="h-6 w-2/3 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" />
            <div className="h-4 w-1/3 animate-pulse rounded-sm bg-surface-sunk motion-reduce:animate-none" />
          </div>
        </SheetHeader>
      )}
    </SideSheet>
  )
}

function TodoDetail({ todo, onClose, onEdit, onOpenApplication }: { todo: Todo; onClose: () => void; onEdit: () => void; onOpenApplication: (id: string) => void }) {
  const { update, remove } = useTodoMutations()
  const today = todayIso()
  const when = todo.due_date ? dueText(todo.due_date, today, todo.done) : null
  const setDone = (done: boolean) =>
    update.mutate({ id: todo.id, body: { done } }, { onError: (err) => toastError(err, "Couldn't save the to-do") })

  return (
    <>
      <SheetHeader className="border-b border-separator p-5 pr-14">
        <SheetTitle className={cn("wrap-anywhere", todo.done && "text-ink-tertiary line-through")}>{todo.title}</SheetTitle>
        <SheetDescription>{todo.done ? "To-do, done" : "To-do"}</SheetDescription>
      </SheetHeader>
      <div className="nice-scroll min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
        <dl className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-callout">
          <dt className="text-ink-secondary">Due</dt>
          <dd className={cn("font-medium", when ? when.tone : "text-ink-tertiary")}>{when ? when.text : "No date"}</dd>
          <dt className="text-ink-secondary">Priority</dt>
          <dd className="flex items-center gap-1.5 font-medium text-ink">
            {todo.priority === "high" ? <Flag aria-hidden="true" className="size-3.5 text-sun-ink" /> : null}
            {PRIORITIES.find((p) => p.value === todo.priority)?.label}
          </dd>
          {todo.application_id && todo.application_label ? (
            <>
              <dt className="text-ink-secondary">Application</dt>
              <dd className="min-w-0">
                <button type="button" onClick={() => onOpenApplication(todo.application_id!)} className="inline-flex max-w-full cursor-pointer items-center gap-1.5 font-medium text-link hover:underline">
                  <OpportunityArt seed={todo.opportunity_id ?? todo.application_id} shape="square" className="size-4 shrink-0 rounded-[4px]" />
                  <span className="truncate">{todo.application_label}</span>
                </button>
              </dd>
            </>
          ) : todo.opportunity_id && todo.opportunity_title ? (
            <>
              <dt className="text-ink-secondary">Opportunity</dt>
              <dd className="min-w-0">
                <Link to={`/opportunities/${todo.opportunity_id}`} className="inline-flex max-w-full items-center gap-1.5 font-medium text-link hover:underline">
                  <OpportunityArt seed={todo.opportunity_id} shape="square" className="size-4 shrink-0 rounded-[4px]" />
                  <span className="truncate">{todo.opportunity_title}</span>
                </Link>
              </dd>
            </>
          ) : null}
        </dl>
        {todo.notes ? <p className="text-callout whitespace-pre-wrap text-ink wrap-anywhere">{todo.notes}</p> : null}
      </div>
      <SheetFooter className="mt-0 flex-row flex-wrap items-center justify-end border-t border-separator p-4 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))]">
        <Button
          size="sm"
          variant="quiet"
          className="mr-auto text-critical hover:bg-critical-soft"
          icon={<Trash2 />}
          onClick={() =>
            remove.mutate(todo.id, {
              onSuccess: () => {
                toastSuccess("Deleted")
                onClose()
              },
              onError: (err) => toastError(err, "Couldn't delete the to-do"),
            })
          }
        >
          Delete
        </Button>
        <Button size="sm" variant="quiet" icon={<Pencil />} onClick={onEdit}>Edit</Button>
        {todo.done ? (
          <Button size="sm" variant="secondary" icon={<RotateCcw />} onClick={() => setDone(false)}>Mark not done</Button>
        ) : (
          <Button
            size="sm"
            variant="primary"
            icon={<Check />}
            onClick={() => {
              setDone(true)
              onClose()
              toast.success("Done", { action: { label: "Undo", onClick: () => setDone(false) } })
            }}
          >
            Mark done
          </Button>
        )}
      </SheetFooter>
    </>
  )
}

function TodoEditForm({ todo, onDone }: { todo: Todo; onDone: () => void }) {
  const { update } = useTodoMutations()
  const [title, setTitle] = React.useState(todo.title)
  const [notes, setNotes] = React.useState(todo.notes)
  const [date, setDate] = React.useState(todo.due_date ?? "")
  const [priority, setPriority] = React.useState<TodoPriority>(todo.priority)
  return (
    <form
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(e) => {
        e.preventDefault()
        update.mutate(
          { id: todo.id, body: { title: title.trim(), notes, due_date: date || null, priority } },
          { onSuccess: onDone, onError: (err) => toastError(err, "Couldn't save the to-do") },
        )
      }}
    >
      <SheetHeader className="border-b border-separator p-5 pr-14">
        <SheetTitle>Edit to-do</SheetTitle>
        <SheetDescription className="sr-only">Change the title, due date, priority or notes.</SheetDescription>
      </SheetHeader>
      <div className="nice-scroll min-h-0 flex-1 space-y-3 overflow-y-auto p-5">
        <Field label="To-do"><Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} required autoFocus /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Due"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <Field label="Priority">
            <Select value={priority} onChange={(e) => setPriority(e.target.value as TodoPriority)}>
              {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Notes"><Textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4000} /></Field>
      </div>
      <SheetFooter className="mt-0 flex-row items-center justify-end border-t border-separator p-4 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))]">
        <Button type="button" size="sm" variant="quiet" onClick={onDone}>Cancel</Button>
        <Button type="submit" size="sm" variant="primary" disabled={update.isPending || !title.trim()}>Save</Button>
      </SheetFooter>
    </form>
  )
}

/** Every to-do in one list, grouped by when it is due. */
export function TodosSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const todos = useTodos("open", open)
  const [showDone, setShowDone] = React.useState(false)
  const done = useTodos("done", open && showDone)
  const today = todayIso()
  const groups = groupTodos(todos.data ?? [], today)

  return (
    <SideSheet open={open} onClose={onClose}>
      <SheetHeader className="border-b border-separator p-5 pr-14">
        <SheetTitle>To-dos</SheetTitle>
        <SheetDescription>The steps that move your applications forward.</SheetDescription>
      </SheetHeader>
      <div className="nice-scroll min-h-0 flex-1 space-y-5 overflow-y-auto p-4 max-sm:pb-[max(1rem,env(safe-area-inset-bottom))] sm:p-5">
        <TodoAdd placeholder="Add a to-do" />
        {todos.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }, (_, i) => <div key={i} className="h-14 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />)}
          </div>
        ) : todos.isError ? (
          <ErrorState compact title="Your to-dos didn't load" description="Try again in a moment." onRetry={() => void todos.refetch()} />
        ) : groups.length === 0 ? (
          <EmptyState compact title="Nothing to do yet" description="Add a to-do above, or add one from any opportunity or application." />
        ) : (
          groups.map((group) => (
            <section key={group.id} aria-labelledby={`todo-group-${group.id}`} className="space-y-1.5">
              <h2 id={`todo-group-${group.id}`} className={cn("flex gap-1.5 text-caption", group.id === "overdue" ? "text-bloom-ink" : "text-ink-tertiary")}>
                {group.label} <span className="tabular-nums">{group.items.length}</span>
              </h2>
              <ul className="overflow-hidden rounded-lg border border-separator bg-surface">
                {group.items.map((todo, i) => <TodoRow key={todo.id} todo={todo} today={today} index={i} />)}
              </ul>
            </section>
          ))
        )}
        <section className="space-y-1.5">
          <button
            type="button"
            aria-expanded={showDone}
            onClick={() => setShowDone((v) => !v)}
            className="flex cursor-pointer items-center gap-1 rounded-sm text-caption text-ink-tertiary hover:text-ink focus-visible:outline-2 focus-visible:outline-focus"
          >
            <ChevronRight aria-hidden="true" className={cn("size-3.5 transition-transform duration-150", showDone && "rotate-90")} />
            Done
          </button>
          {showDone ? (
            done.isLoading ? (
              <div className="h-14 animate-pulse rounded-lg bg-surface-sunk motion-reduce:animate-none" />
            ) : !done.data?.length ? (
              <p className="text-footnote text-ink-secondary">Nothing done yet.</p>
            ) : (
              <ul className="overflow-hidden rounded-lg border border-separator bg-surface">
                {done.data.map((todo, i) => <TodoRow key={todo.id} todo={todo} today={today} index={i} />)}
              </ul>
            )
          ) : null}
        </section>
      </div>
    </SideSheet>
  )
}

/** The rail's Create: a to-do, dated to the day in view unless changed. */
export function CreateTodoDialog({ open, date, onClose }: { open: boolean; date: string; onClose: () => void }) {
  const { create } = useTodoMutations()
  const [title, setTitle] = React.useState("")
  const [due, setDue] = React.useState(date)
  const [notes, setNotes] = React.useState("")
  const [priority, setPriority] = React.useState<TodoPriority>("normal")
  const [wasOpen, setWasOpen] = React.useState(open)
  if (open !== wasOpen) {
    setWasOpen(open)
    if (open) {
      setTitle("")
      setDue(date)
      setNotes("")
      setPriority("normal")
    }
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      {open ? (
        <DialogContent className="max-w-md" onClose={onClose}>
          <form
            className="flex min-h-0 flex-col"
            onSubmit={(e) => {
              e.preventDefault()
              if (!title.trim()) return
              create.mutate(
                { title: title.trim(), due_date: due || null, notes, priority },
                {
                  onSuccess: () => {
                    toastSuccess("To-do added")
                    onClose()
                  },
                  onError: (err) => toastError(err, "Couldn't add the to-do"),
                },
              )
            }}
          >
            <DialogHeader><DialogTitle>New to-do</DialogTitle></DialogHeader>
            <DialogBody className="space-y-3">
              <Field label="To-do"><Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} required autoFocus placeholder="Ask two referees for letters" /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Due"><Input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
                <Field label="Priority">
                  <Select value={priority} onChange={(e) => setPriority(e.target.value as TodoPriority)}>
                    {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                  </Select>
                </Field>
              </div>
              <Field label="Notes"><Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4000} /></Field>
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="quiet" onClick={onClose}>Cancel</Button>
              <Button type="submit" variant="primary" disabled={create.isPending || !title.trim()}>Add to-do</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      ) : null}
    </Dialog>
  )
}

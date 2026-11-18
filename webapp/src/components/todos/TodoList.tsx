import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import { Check, Flag, Pencil, PanelRightOpen, Plus, CalendarClock, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button, Field, Input, OpportunityArt, Select, Textarea, cn } from "@blesser/ui"
import { useTodoMutations } from "../../lib/opportunities"
import { toastError } from "../../lib/toast"
import type { Todo, TodoCreate, TodoPriority } from "../../lib/types"
import { ActionContextMenu, ActionMenuButton, type MenuAction } from "../ui/menu"
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"

/** Local yyyy-mm-dd: due dates are calendar days, not instants. */
export function todayIso(offsetDays = 0): string {
  const now = new Date(Date.now() + offsetDays * 86_400_000)
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(toIso + "T00:00:00Z") - Date.parse(fromIso + "T00:00:00Z")) / 86_400_000)
}

export type TodoGroup = { id: "overdue" | "today" | "week" | "later" | "someday"; label: string; items: Todo[] }

export function groupTodos(todos: Todo[], today: string): TodoGroup[] {
  const groups: TodoGroup[] = [
    { id: "overdue", label: "Overdue", items: [] },
    { id: "today", label: "Today", items: [] },
    { id: "week", label: "This week", items: [] },
    { id: "later", label: "Later", items: [] },
    { id: "someday", label: "No date", items: [] },
  ]
  const by = Object.fromEntries(groups.map((g) => [g.id, g]))
  for (const t of todos) {
    if (!t.due_date) by.someday.items.push(t)
    else {
      const d = daysBetween(today, t.due_date)
      by[d < 0 ? "overdue" : d === 0 ? "today" : d <= 7 ? "week" : "later"].items.push(t)
    }
  }
  return groups.filter((g) => g.items.length > 0)
}

function due(dueDate: string, today: string): { text: string; tone: string } {
  const d = daysBetween(today, dueDate)
  if (d < 0) return { text: d === -1 ? "1 day overdue" : `${-d} days overdue`, tone: "text-bloom-ink" }
  if (d === 0) return { text: "Today", tone: "text-sun-ink" }
  if (d === 1) return { text: "Tomorrow", tone: "" }
  if (d <= 7) return { text: `In ${d} days`, tone: "" }
  return { text: new Date(dueDate + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" }), tone: "" }
}

const PRIORITIES: { value: TodoPriority; label: string }[] = [
  { value: "high", label: "High" },
  { value: "normal", label: "Normal" },
  { value: "low", label: "Low" },
]

const DUE_OPTIONS = [
  { value: "today", label: "Today" },
  { value: "tomorrow", label: "Tomorrow" },
  { value: "week", label: "Next week" },
  { value: "none", label: "No date" },
]

function dueChoice(todo: Todo, today: string): string {
  if (!todo.due_date) return "none"
  const d = daysBetween(today, todo.due_date)
  return d === 0 ? "today" : d === 1 ? "tomorrow" : d === 7 ? "week" : ""
}

const DUE_DATE: Record<string, () => string | null> = {
  today: () => todayIso(),
  tomorrow: () => todayIso(1),
  week: () => todayIso(7),
  none: () => null,
}

/** One to-do, the same on the To-dos page and inside an application. */
export function TodoRow({ todo, today, showLink = true, index = 0 }: { todo: Todo; today: string; showLink?: boolean; index?: number }) {
  const { update, remove } = useTodoMutations()
  const navigate = useNavigate()
  const [ticked, setTicked] = React.useState(todo.done)
  const [editing, setEditing] = React.useState(false)
  const timer = React.useRef<number | undefined>(undefined)
  React.useEffect(() => () => window.clearTimeout(timer.current), [])
  const set = (body: Parameters<typeof update.mutate>[0]["body"]) =>
    update.mutate({ id: todo.id, body }, { onError: (err) => toastError(err, "Couldn't save the to-do") })

  const toggle = () => {
    if (todo.done) {
      setTicked(false)
      set({ done: false })
      return
    }
    setTicked(true)
    // Let the check and strike land before the row folds away.
    timer.current = window.setTimeout(() => {
      set({ done: true })
      toast.success("Done", { action: { label: "Undo", onClick: () => set({ done: false }) } })
    }, 600)
  }

  const linked = todo.application_id && todo.application_label
    ? { to: `/applications?open=${todo.application_id}`, label: todo.application_label, seed: todo.opportunity_id ?? todo.application_id }
    : todo.opportunity_id && todo.opportunity_title
      ? { to: `/opportunities/${todo.opportunity_id}`, label: todo.opportunity_title, seed: todo.opportunity_id }
      : null

  const actions: MenuAction[] = [
    { label: "Edit", icon: <Pencil />, onSelect: () => setEditing(true) },
    { kind: "radio", label: "Due", icon: <CalendarClock />, value: dueChoice(todo, today), options: DUE_OPTIONS, onChange: (v) => set({ due_date: DUE_DATE[v]() }) },
    { kind: "radio", label: "Priority", icon: <Flag />, value: todo.priority, options: PRIORITIES, onChange: (v) => set({ priority: v as TodoPriority }) },
    ...(linked ? [{ label: todo.application_id ? "Open application" : "Open opportunity", icon: <PanelRightOpen />, onSelect: () => navigate(linked.to) }] : []),
    { kind: "separator" },
    { label: "Delete", icon: <Trash2 />, danger: true, onSelect: () => remove.mutate(todo.id, { onError: (err) => toastError(err, "Couldn't delete the to-do") }) },
  ]
  const when = todo.due_date ? due(todo.due_date, today) : null
  const done = ticked || todo.done

  return (
    <ActionContextMenu actions={actions}>
      <li
        style={{ "--i": index } as React.CSSProperties}
        className={cn("bl-enter grid grid-cols-[20px_minmax(0,1fr)_auto] items-start gap-3 border-t border-separator px-4 py-3 first:border-t-0 hover:bg-highlight", ticked && !todo.done && "opacity-60 transition-opacity duration-500")}
      >
        <button
          type="button"
          role="checkbox"
          aria-checked={done}
          aria-label={done ? `Mark "${todo.title}" not done` : `Mark "${todo.title}" done`}
          onClick={toggle}
          className={cn(
            "mt-px grid size-5 cursor-pointer place-items-center rounded-full border-[1.5px] transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
            done ? "border-forest bg-forest text-on-forest" : "border-input-border-hover bg-surface hover:border-control-border",
          )}
        >
          {done ? <Check className="size-3" strokeWidth={3} aria-hidden="true" /> : null}
        </button>
        <div className="min-w-0">
          <p className={cn("text-[15px]/5 font-medium text-ink wrap-anywhere", done && "text-ink-tertiary line-through")}>
            {todo.priority === "high" && !done ? <Flag className="mr-1.5 inline size-3.5 align-[-2px] text-sun-ink" aria-label="High priority" /> : null}
            {todo.title}
          </p>
          {when || (linked && showLink) ? (
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-footnote font-medium text-ink-secondary">
              {when ? <span className={cn(!done && when.tone)}>{when.text}</span> : null}
              {linked && showLink ? (
                <Link to={linked.to} className="inline-flex min-w-0 items-center gap-1.5 hover:text-link hover:underline">
                  <OpportunityArt seed={linked.seed} shape="square" className="size-4 shrink-0 rounded-[4px]" />
                  <span className="truncate">{linked.label}</span>
                </Link>
              ) : null}
            </div>
          ) : null}
        </div>
        <ActionMenuButton actions={actions} label={`More for ${todo.title}`} className="-my-1" />
        <EditTodo todo={todo} open={editing} onClose={() => setEditing(false)} />
      </li>
    </ActionContextMenu>
  )
}

function EditTodo({ todo, open, onClose }: { todo: Todo; open: boolean; onClose: () => void }) {
  const { update } = useTodoMutations()
  const [title, setTitle] = React.useState(todo.title)
  const [notes, setNotes] = React.useState(todo.notes)
  const [date, setDate] = React.useState(todo.due_date ?? "")
  const [priority, setPriority] = React.useState<TodoPriority>(todo.priority)
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      {open ? (
        <DialogContent className="max-w-md" onClose={onClose}>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              update.mutate(
                { id: todo.id, body: { title: title.trim(), notes, due_date: date || null, priority } },
                { onSuccess: onClose, onError: (err) => toastError(err, "Couldn't save the to-do") },
              )
            }}
          >
            <DialogHeader><DialogTitle>Edit to-do</DialogTitle></DialogHeader>
            <DialogBody className="space-y-3">
              <Field label="To-do"><Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} required /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Due"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
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
              <Button type="submit" variant="primary" disabled={update.isPending || !title.trim()}>Save</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      ) : null}
    </Dialog>
  )
}

/** The quick-add composer; `link` files the new to-do under an application or opportunity. */
export function TodoAdd({ link, placeholder = "Add a to-do, e.g. Ask two referees for letters", className }: {
  link?: Pick<TodoCreate, "application_id" | "opportunity_id">
  placeholder?: string
  className?: string
}) {
  const { create } = useTodoMutations()
  const [title, setTitle] = React.useState("")
  const [date, setDate] = React.useState("")
  const [priority, setPriority] = React.useState<TodoPriority>("normal")
  return (
    <form
      className={cn("flex flex-wrap items-center gap-2 rounded-md border border-input-border bg-surface py-1.5 pr-1.5 pl-4 shadow-elevation-1 transition-[border-color,box-shadow] duration-150 focus-within:border-focus focus-within:shadow-[0_0_0_3px_var(--focus-soft)]", className)}
      onSubmit={(e) => {
        e.preventDefault()
        if (!title.trim()) return
        create.mutate(
          { title: title.trim(), due_date: date || null, priority, ...link },
          {
            onSuccess: () => { setTitle(""); setDate(""); setPriority("normal") },
            onError: (err) => toastError(err, "Couldn't add the to-do"),
          },
        )
      }}
    >
      <input
        aria-label="New to-do"
        placeholder={placeholder}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        maxLength={300}
        className="h-9 min-w-[12rem] flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-tertiary"
      />
      <div className="flex items-center gap-1.5">
        <input
          aria-label="Due date"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className={cn("h-8 rounded-full bg-surface-sunk px-3 text-footnote font-medium outline-none focus-visible:outline-2 focus-visible:outline-focus", date ? "text-ink" : "text-ink-tertiary")}
        />
        <button
          type="button"
          aria-pressed={priority === "high"}
          aria-label="High priority"
          onClick={() => setPriority((p) => (p === "high" ? "normal" : "high"))}
          className={cn("grid size-8 cursor-pointer place-items-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-focus", priority === "high" ? "bg-sun-soft text-sun-ink" : "text-ink-tertiary hover:bg-highlight")}
        >
          <Flag className="size-4" aria-hidden="true" />
        </button>
        <Button type="submit" size="sm" variant="primary" icon={<Plus />} disabled={create.isPending || !title.trim()}></Button>
      </div>
    </form>
  )
}

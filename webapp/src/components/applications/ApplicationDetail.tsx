import * as React from "react"
import { ApplicationStatus, Button, Field, Input, Textarea, cn, type ApplicationStage } from "@blesser/ui"
import { useApplicationMutations } from "../../lib/applications"
import { useTodos } from "../../lib/opportunities"
import { toastError } from "../../lib/toast"
import type { Application, ApplicationStatus as Status, RequirementItem } from "../../lib/types"
import { TodoAdd, TodoRow, todayIso } from "../todos/TodoList"
import { Checkbox } from "../ui/checkbox"

const stage = (status: Status): ApplicationStage => (status === "rejected" ? "not-this-time" : status)

/** The editable application detail shared by the drawer and the full page. */
export function ApplicationDetail({ app }: { app: Application }) {
  const { update } = useApplicationMutations()
  const [notes, setNotes] = React.useState(app.notes)
  const [deadline, setDeadline] = React.useState(app.deadline_date ?? "")
  const [requirements, setRequirements] = React.useState<RequirementItem[]>(app.requirements)
  const [newItem, setNewItem] = React.useState("")
  const save = (body: Parameters<typeof update.mutate>[0]["body"]) =>
    update.mutate({ id: app.id, body }, { onError: (err) => toastError(err, "Couldn't save") })

  return (
    <div className="space-y-4">
      <ApplicationStatus status={stage(app.status)} />
      {app.benefits ? <p className="text-callout font-semibold text-ink">{app.benefits}</p> : null}
      <Field label="Deadline">
        <Input
          type="date"
          value={deadline}
          onChange={(e) => setDeadline(e.target.value)}
          onBlur={() => deadline !== (app.deadline_date ?? "") && save({ deadline_date: deadline || null })}
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
      <ApplicationTodos app={app} />
      <Field label="Notes">
        <Textarea
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => notes !== app.notes && save({ notes })}
        />
      </Field>
    </div>
  )
}

function ApplicationTodos({ app }: { app: Application }) {
  const todos = useTodos("open")
  const today = todayIso()
  const mine = (todos.data ?? []).filter((t) => t.application_id === app.id)
  return (
    <section aria-labelledby="app-todos-heading" className="space-y-2">
      <h3 id="app-todos-heading" className="text-headline text-ink">To-dos</h3>
      {mine.length ? (
        <ul className="overflow-hidden rounded-lg border border-separator bg-surface">
          {mine.map((todo, i) => <TodoRow key={todo.id} todo={todo} today={today} index={i} showLink={false} />)}
        </ul>
      ) : null}
      <TodoAdd link={{ application_id: app.id }} placeholder="Add a step, e.g. Ask for two references" />
    </section>
  )
}

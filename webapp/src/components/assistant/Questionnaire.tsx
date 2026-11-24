import { useId, useState } from "react"
import { Button, Field, cn } from "@blesser/ui"
import { Checkbox } from "../ui/checkbox"
import { DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import type { Answers, PendingCall, Question } from "../../lib/assistant"
import { OTHER, answersOf, emptyDraft, problems, type Draft } from "../../lib/questionnaire"

const ROW = "flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-callout text-ink transition-colors hover:bg-highlight has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-focus"

/** The Assistant's questions, answered in a modal. Skipping lets the Assistant choose. */
export function QuestionnaireDialog({ call, sending, onSend, onSkip, onClose }: {
  call: PendingCall
  sending: boolean
  onSend: (answers: Answers) => void
  onSkip: () => void
  onClose: () => void
}) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [tried, setTried] = useState(false)
  const issues = problems(call.questions, drafts)
  const ready = !Object.keys(issues).length

  function edit(id: string, change: Partial<Draft>) {
    setDrafts((current) => ({ ...current, [id]: { ...(current[id] ?? emptyDraft()), ...change } }))
  }

  return (
    <DialogContent onClose={onClose}>
      <form className="flex min-h-0 flex-1 flex-col" onSubmit={(event) => {
        event.preventDefault()
        setTried(true)
        if (ready && !sending) onSend(answersOf(call.questions, drafts))
      }}>
        <DialogHeader>
          <DialogTitle className="wrap-anywhere">{call.summary}</DialogTitle>
          <DialogDescription>Answer what you can, or skip and let the Assistant choose.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-6">
          {call.questions.map((question) => (
            <QuestionField key={question.id} question={question} draft={drafts[question.id] ?? emptyDraft()}
              error={tried ? issues[question.id] : undefined} onChange={(change) => edit(question.id, change)} />
          ))}
        </DialogBody>
        <DialogFooter>
          <Button variant="quiet" disabled={sending} onClick={onSkip}>Skip</Button>
          <Button type="submit" variant="primary" disabled={sending}>Send answers</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}

function QuestionField({ question, draft, error, onChange }: {
  question: Question
  draft: Draft
  error?: string
  onChange: (change: Partial<Draft>) => void
}) {
  const name = useId()
  const errorId = `${name}-error`
  const optional = question.required ? null : <span className="font-normal text-ink-secondary"> (optional)</span>

  if (question.type === "text" || question.type === "date") {
    return (
      <Field label={question.prompt} type={question.type === "date" ? "date" : "text"} maxLength={300}
        required={question.required} value={draft.text} error={error}
        hint={question.required ? undefined : "Optional"}
        onChange={(event) => onChange({ text: event.target.value })} />
    )
  }

  const multiple = question.type === "multiple"
  const hint = multiple && question.max_choices ? `Choose up to ${question.max_choices}.` : multiple ? "Choose all that apply." : null
  return (
    <fieldset aria-describedby={error ? errorId : undefined} className="min-w-0">
      <legend className="mb-1 text-sm leading-5 font-semibold text-ink">{question.prompt}{optional}</legend>
      {hint ? <p className="mb-1.5 text-footnote text-ink-secondary">{hint}</p> : null}
      <div className="-mx-3 flex flex-col">
        {question.options.map((option) => multiple ? (
          <label key={option} className={ROW}>
            <Checkbox checked={draft.choices.includes(option)}
              onCheckedChange={(on) => onChange({ choices: on ? [...draft.choices, option] : draft.choices.filter((c) => c !== option) })} />
            <span className="min-w-0 wrap-anywhere">{option}</span>
          </label>
        ) : (
          <label key={option} className={ROW}>
            <Radio name={name} checked={!draft.other && draft.choice === option} onChange={() => onChange({ choice: option, other: false })} />
            <span className="min-w-0 wrap-anywhere">{option}</span>
          </label>
        ))}
        {question.allow_other ? (
          <label className={ROW}>
            {multiple
              ? <Checkbox checked={draft.other} onCheckedChange={(on) => onChange({ other: on === true })} />
              : <Radio name={name} checked={draft.other} onChange={() => onChange({ other: true })} />}
            <span>{OTHER}</span>
          </label>
        ) : null}
      </div>
      {draft.other ? (
        <input aria-label={`${question.prompt} ${OTHER.toLowerCase()}`} autoFocus maxLength={300} value={draft.text}
          onChange={(event) => onChange({ text: event.target.value })}
          className="mt-1 h-control-md w-full min-w-0 rounded-sm border border-input-border bg-surface px-3.5 text-body text-ink outline-none hover:border-input-border-hover focus-visible:outline-2 focus-visible:outline-focus" />
      ) : null}
      {error ? <p id={errorId} className="mt-1.5 text-footnote font-medium text-critical">{error}</p> : null}
    </fieldset>
  )
}

function Radio({ name, checked, onChange }: { name: string; checked: boolean; onChange: () => void }) {
  return (
    <span className="relative grid size-4 shrink-0 place-items-center">
      <input type="radio" name={name} checked={checked} onChange={onChange} className="peer sr-only" />
      <span aria-hidden="true" className={cn(
        "size-4 rounded-full border bg-surface transition-colors",
        checked ? "border-[5px] border-forest" : "border-input-border-hover",
      )} />
    </span>
  )
}

/** The waiting card in the chat: approve a change, or open the questions again. */
export function PendingCard({ call, working, onDecide, onOpenQuestions }: {
  call: PendingCall
  working: boolean
  onDecide: (approved: boolean) => void
  onOpenQuestions: () => void
}) {
  if (call.type === "questions") {
    const count = call.questions.length
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-separator bg-surface p-4">
        <div className="min-w-0">
          <p className="text-callout font-semibold text-ink wrap-anywhere">{call.summary}</p>
          <p className="text-footnote text-ink-secondary">{count === 1 ? "1 question" : `${count} questions`}</p>
        </div>
        <Button size="sm" variant="primary" disabled={working} onClick={onOpenQuestions}>Answer</Button>
      </div>
    )
  }
  return (
    <div className="space-y-3 rounded-md border border-separator bg-surface p-4">
      <div className="space-y-1">
        <p className="text-callout font-semibold text-ink wrap-anywhere">{call.summary}</p>
        {call.note ? <p className="nice-scroll max-h-64 overflow-y-auto text-callout whitespace-pre-wrap text-ink-secondary wrap-anywhere">{call.note}</p> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant={call.tone === "danger" ? "danger" : "primary"} disabled={working} onClick={() => onDecide(true)}>
          {call.action || "Approve"}
        </Button>
        <Button size="sm" variant="quiet" disabled={working} onClick={() => onDecide(false)}>Not now</Button>
      </div>
    </div>
  )
}

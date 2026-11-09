import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Plus, Search, Trash2 } from "lucide-react"
import { Button, Field, Input, Textarea, cn } from "@blesser/ui"
import { SettingsSection } from "../../components/settings/controls"
import { EmptyState, ErrorState } from "../../components/feedback/EmptyState"
import { ConfirmDialog, KitSkeleton, SelectField, TagInput } from "../../components/kit/parts"
import { formatAgo } from "../../lib/format"
import { KIT_PITCH, limitFromQuestion, limitStatus, normalizeAnswer } from "../../lib/kit"
import { createAnswer, deleteAnswer, putAnswer, useAnswers, useProjects } from "../../lib/kitApi"
import type { Answer, AnswerInput, Project } from "../../lib/kitTypes"
import { useDraft } from "../../lib/useDraft"
import { toastError, toastSuccess } from "../../lib/toast"

type Selection = { key: string; answer: Answer | null }

export function AnswersTab() {
  return (
    <SettingsSection id="kit-answers" title="Answers" description="Your best answers to the questions forms keep asking, ready to reuse and trim to each word limit.">
      <AnswersBody />
    </SettingsSection>
  )
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = React.useState(value)
  React.useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(t)
  }, [value, ms])
  return v
}

function AnswersBody() {
  const [text, setText] = React.useState("")
  const q = useDebounced(text.trim(), 250)
  const [projectId, setProjectId] = React.useState("")
  const answers = useAnswers(q, projectId)
  const projects = useProjects()
  const [selected, setSelected] = React.useState<Selection | null>(null)
  const counter = React.useRef(0)
  const list = answers.data ?? []
  const projectList = projects.data ?? []
  const filtering = !!(q || projectId)

  const startNew = () => {
    counter.current += 1
    setSelected({ key: `new-${counter.current}`, answer: null })
  }

  if (answers.isError && !answers.data) {
    return <ErrorState title="Your answers didn't load" description="Check your connection and try again." onRetry={() => void answers.refetch()} />
  }
  if (answers.isLoading) return <KitSkeleton rows={3} />
  if (!filtering && list.length === 0 && !selected) {
    return (
      <EmptyState
        title="Save your first answer"
        description={`"Describe your solution in 100 words." "Why this fellowship?" Write your best answer once and reuse it. ${KIT_PITCH}`}
        action={<Button size="sm" variant="brand" icon={<Plus />} onClick={startNew}>New answer</Button>}
      />
    )
  }

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-6">
      <div className={cn("min-w-0 space-y-3", selected && "max-lg:hidden")}>
        <div className="flex gap-2">
          <div className="relative min-w-0 flex-1">
            <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-tertiary" />
            <Input
              type="search"
              aria-label="Search answers"
              placeholder="Search questions and answers"
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="h-control-sm pl-9 text-callout"
            />
          </div>
          <Button size="sm" variant="secondary" icon={<Plus />} onClick={startNew} aria-label="New answer" className="sm:hidden" />
          <Button size="sm" variant="secondary" icon={<Plus />} onClick={startNew} className="max-sm:hidden">New</Button>
        </div>
        {projectList.length ? (
          <select
            aria-label="Filter by project"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="select-chevron h-control-sm w-full cursor-pointer appearance-none rounded-sm border border-control-border bg-surface pr-9 pl-3 text-footnote text-ink focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus"
          >
            <option value="">All projects</option>
            {projectList.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        ) : null}
        {list.length === 0 ? (
          <p className="rounded-lg border border-separator bg-surface px-4 py-6 text-center text-footnote text-ink-secondary">No answers match.</p>
        ) : (
          <ul aria-label="Answers" className={cn("divide-y divide-separator overflow-hidden rounded-lg border border-separator bg-surface", answers.isFetching && "opacity-80")}>
            {list.map((a) => {
              const on = selected?.answer?.id === a.id
              const project = projectList.find((p) => p.id === a.project_id)
              return (
                <li key={a.id}>
                  <button
                    type="button"
                    aria-current={on ? "true" : undefined}
                    onClick={() => setSelected({ key: a.id, answer: a })}
                    className={cn(
                      "block w-full cursor-pointer px-4 py-3 text-left transition-colors duration-160 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus",
                      on ? "bg-forest-soft/50" : "hover:bg-surface-sunk/70",
                    )}
                  >
                    <span className="line-clamp-2 text-callout font-medium text-ink">{a.question || "Untitled question"}</span>
                    <span className="mt-1 line-clamp-1 text-footnote text-ink-secondary">{a.answer || "No answer yet"}</span>
                    <span className="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-caption text-ink-tertiary">
                      <span className="tabular-nums">{a.word_count} {a.word_count === 1 ? "word" : "words"}</span>
                      {project ? <><span aria-hidden="true">·</span><span className="truncate">{project.name}</span></> : null}
                      {a.tags.slice(0, 2).map((t) => <React.Fragment key={t}><span aria-hidden="true">·</span><span>{t}</span></React.Fragment>)}
                      <span aria-hidden="true">·</span>
                      <span>{formatAgo(a.updated_at)}</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div className={cn("min-w-0", !selected && "max-lg:hidden")}>
        {selected ? (
          <AnswerEditor
            key={selected.key}
            initial={selected.answer}
            projects={projectList}
            onBack={() => setSelected(null)}
            onDeleted={() => setSelected(null)}
          />
        ) : (
          <div className="flex h-full min-h-48 items-center justify-center rounded-lg border border-dashed border-separator px-6 text-center text-footnote text-ink-secondary">
            Choose an answer to edit, or start a new one.
          </div>
        )}
      </div>
    </div>
  )
}

const EMPTY: AnswerInput = { question: "", answer: "", tags: [], project_id: null }

function AnswerEditor({ initial, projects, onBack, onDeleted }: { initial: Answer | null; projects: Project[]; onBack: () => void; onDeleted: () => void }) {
  const client = useQueryClient()
  const id = React.useRef(initial?.id ?? null)
  const [removing, setRemoving] = React.useState(false)
  const [savedAt, setSavedAt] = React.useState(initial?.updated_at ?? null)
  const [savedId, setSavedId] = React.useState(initial?.id ?? null)

  const save = React.useCallback(
    async (payload: AnswerInput) => {
      const saved = id.current ? await putAnswer(id.current, payload) : await createAnswer(payload)
      id.current = saved.id
      setSavedId(saved.id)
      setSavedAt(saved.updated_at)
      void client.invalidateQueries({ queryKey: ["kit", "answers"] })
      return saved
    },
    [client],
  )

  const start: AnswerInput = initial ? { question: initial.question, answer: initial.answer, tags: initial.tags, project_id: initial.project_id } : EMPTY
  const { draft: a, update: set, discard } = useDraft<AnswerInput, AnswerInput>(start, normalizeAnswer, save, { canSave: (p) => !!(p.question && p.answer) })
  const limit = limitFromQuestion(a.question)
  const status = limitStatus(a.answer, limit)
  const unit = limit?.unit === "characters" ? "characters" : status.used === 1 ? "word" : "words"
  const questionRef = React.useRef<HTMLTextAreaElement | null>(null)
  const counterId = React.useId()

  React.useEffect(() => {
    if (!initial) questionRef.current?.focus()
  }, [initial])

  return (
    <div className="rounded-lg border border-separator bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-separator px-4 py-2 sm:px-5">
        <Button size="sm" variant="quiet" icon={<ArrowLeft />} onClick={onBack} className="-ml-2 lg:hidden [&_svg]:size-4">All answers</Button>
        <p className="text-footnote text-ink-tertiary max-lg:hidden">
          {savedId && savedAt ? `Edited ${formatAgo(savedAt)}` : "New answer"}
        </p>
        <Button
          size="sm"
          variant="quiet"
          icon={<Trash2 />}
          aria-label="Delete answer"
          className="size-8 text-ink-tertiary hover:text-critical [&_svg]:size-4"
          onClick={() => (savedId ? setRemoving(true) : (discard(), onDeleted()))}
        />
      </div>
      <div className="space-y-4 px-4 py-4 sm:px-5">
        <Field label="Question" hint={a.question.trim() && a.answer.trim() ? "Put the limit in the question, such as \"in 100 words\", and the count checks it." : "Saves once it has a question and an answer."}>
          <Textarea
            ref={questionRef}
            value={a.question}
            onChange={(e) => set({ question: e.target.value })}
            rows={2}
            maxLength={500}
            placeholder="Describe your solution in 100 words."
            className="min-h-0 text-callout font-medium"
          />
        </Field>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor={`${counterId}-answer`} className="text-sm leading-5 font-semibold text-ink">Answer</label>
            <span
              id={counterId}
              aria-live="polite"
              className={cn("text-footnote tabular-nums", status.over ? "font-semibold text-critical" : status.near ? "text-caution" : "text-ink-secondary")}
            >
              {limit ? `${status.used} / ${limit.count} ${limit.unit}` : `${status.used} ${unit}`}
              {status.over ? `, ${status.used - limit!.count} over` : ""}
            </span>
          </div>
          <Textarea
            id={`${counterId}-answer`}
            aria-describedby={counterId}
            aria-invalid={status.over || undefined}
            value={a.answer}
            onChange={(e) => set({ answer: e.target.value })}
            rows={11}
            className="min-h-40 text-callout leading-6"
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <TagInput label="Tags" values={a.tags} onChange={(tags) => set({ tags })} placeholder="solution, impact" />
          {projects.length ? (
            <SelectField
              label="Project"
              value={a.project_id ?? ""}
              onChange={(v) => set({ project_id: v || null })}
              placeholder="Not tied to a project"
              options={projects.map((p) => ({ value: p.id, label: p.name }))}
            />
          ) : null}
        </div>
      </div>
      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title="Delete this answer?"
        description="It goes for good. This can't be undone."
        confirm="Delete answer"
        onConfirm={async () => {
          if (!id.current) return
          try {
            discard()
            await deleteAnswer(id.current)
            await client.invalidateQueries({ queryKey: ["kit", "answers"] })
            toastSuccess("Answer deleted")
            onDeleted()
          } catch (err) {
            toastError(err, "Couldn't delete the answer")
          }
        }}
      />
    </div>
  )
}

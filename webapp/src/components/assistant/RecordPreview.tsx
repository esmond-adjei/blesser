import { useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { buttonVariants, cn } from "@blesser/ui"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../ui/shadcn/sheet"
import { useIsMobile } from "../../hooks/use-mobile"
import type { AssistantSource } from "../../lib/assistant"
import { useAnswers, useDocuments, useProjects } from "../../lib/kitApi"
import { useTodos, useTrackedOpportunities } from "../../lib/opportunities"
import type { Opportunity } from "../../lib/types"
import { ApplicationSheet } from "../../pages/Applications"
import { OpportunityDetail, TodoDialog } from "../../pages/Opportunities"
import { TodoSheet } from "../calendar/TodoSheets"
import { ShareDialog } from "../share/ShareDialog"
import { useCopy } from "../../lib/useCopy"
import { Markdown } from "./Markdown"

export type Ref = Pick<AssistantSource, "kind" | "id"> & { slug?: string }

export function RecordPreview({ target, onClose, onSwap }: { target: Ref | null; onClose: () => void; onSwap: (ref: Ref) => void }) {
  const tracked = useTrackedOpportunities()
  const [todoFor, setTodoFor] = useState<Opportunity | null>(null)
  const [shareFor, setShareFor] = useState<Opportunity | null>(null)
  const kind = target?.kind
  return (
    <>
      <OpportunityDetail id={kind === "opportunity" ? target?.slug || target?.id || null : null} tracked={tracked.data} onClose={onClose} onTodo={setTodoFor} onShare={setShareFor} />
      <ApplicationSheet id={kind === "application" ? target?.id ?? null : null} onClose={onClose} />
      <TodoPreview id={kind === "todo" ? target?.id ?? null : null} onClose={onClose} onOpenApplication={(id) => onSwap({ kind: "application", id })} />
      <KitPreview target={kind === "project" || kind === "answer" || kind === "document" ? target : null} onClose={onClose} />
      <TodoDialog opp={todoFor} onClose={() => setTodoFor(null)} />
      <ShareDialog opp={shareFor} onClose={() => setShareFor(null)} />
    </>
  )
}

function TodoPreview({ id, onClose, onOpenApplication }: { id: string | null; onClose: () => void; onOpenApplication: (id: string) => void }) {
  const todos = useTodos("all", !!id)
  const todo = id ? todos.data?.find((row) => row.id === id) ?? null : null
  return <TodoSheet todo={todo} loading={!!id && todos.isPending} onClose={onClose} onOpenApplication={onOpenApplication} />
}

const PROJECT_FIELDS: [string, string][] = [
  ["problem", "Problem"], ["solution", "Solution"], ["target_customers", "Customers"], ["business_model", "Business model"],
  ["traction", "Traction"], ["impact", "Impact"], ["use_of_funds", "Use of funds"],
]

function KitPreview({ target, onClose }: { target: Ref | null; onClose: () => void }) {
  const kind = target?.kind
  const projects = useProjects()
  const documents = useDocuments()
  const answers = useAnswers("", "")
  const phone = useIsMobile()
  let title = ""
  let subtitle = ""
  let href = "/kit"
  let body: ReactNode = null
  let copy = ""
  if (kind === "project") {
    const project = projects.data?.find((row) => row.id === target?.id)
    title = project?.name ?? ""
    subtitle = project?.tagline ?? ""
    href = `/kit/projects/${target?.id}`
    body = project ? <Fields rows={[["Stage", sentence(project.stage)], ["Sector", project.sector], ...PROJECT_FIELDS.map(([key, label]): [string, string] => [label, String((project as unknown as Record<string, unknown>)[key] ?? "")])]} /> : null
  } else if (kind === "answer") {
    const answer = answers.data?.find((row) => row.id === target?.id)
    title = answer?.question ?? ""
    subtitle = answer ? `${answer.word_count} words` : ""
    href = "/kit/answers"
    copy = answer?.answer ?? ""
    body = answer ? <Markdown text={answer.answer} /> : null
  } else if (kind === "document") {
    const doc = documents.data?.find((row) => row.id === target?.id)
    title = doc?.title ?? ""
    subtitle = doc ? sentence(doc.kind) : ""
    href = "/kit/documents"
    body = doc ? <Fields rows={[["File", doc.filename], ["Size", `${Math.max(1, Math.round(doc.size_bytes / 1024))} KB`], ["Default", doc.is_default ? "Yes" : "No"]]} /> : null
  }
  const loading = (kind === "project" && projects.isPending) || (kind === "answer" && answers.isPending) || (kind === "document" && documents.isPending)
  return (
    <Sheet open={!!target} onOpenChange={(open) => !open && onClose()}>
      {target ? (
        <SheetContent side={phone ? "bottom" : "right"} className="gap-0 max-sm:h-[92dvh] sm:w-full sm:max-w-xl">
          <SheetHeader className="border-b border-separator p-5 pr-16">
            <SheetTitle className="wrap-anywhere">{title || (loading ? "Loading" : "Not found")}</SheetTitle>
            <SheetDescription>{subtitle || (kind ? `Apply kit ${kind}` : "")}</SheetDescription>
          </SheetHeader>
          <div className="nice-scroll min-h-0 flex-1 overflow-y-auto p-5">
            {body ?? <p className="text-callout text-ink-secondary">{loading ? "Loading" : "This record may have been deleted."}</p>}
          </div>
          <footer className="flex flex-wrap gap-2 border-t border-separator p-4">
            <Link to={href} onClick={onClose} className={buttonVariants({ size: "sm", variant: "primary" })}>Open in Apply kit</Link>
            {copy ? <CopyText text={copy} /> : null}
          </footer>
        </SheetContent>
      ) : null}
    </Sheet>
  )
}

const sentence = (value: string) => value.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())

function CopyText({ text }: { text: string }) {
  const { copied, copy } = useCopy(() => text)
  return <button type="button" onClick={() => void copy()} className={cn(buttonVariants({ size: "sm", variant: "secondary" }))}>{copied ? "Copied" : "Copy answer"}</button>
}

function Fields({ rows }: { rows: [string, string][] }) {
  const shown = rows.filter(([, value]) => value?.trim())
  if (!shown.length) return <p className="text-callout text-ink-secondary">Nothing filled in yet.</p>
  return (
    <dl className="space-y-4">
      {shown.map(([label, value]) => (
        <div key={label}>
          <dt className="text-caption font-medium text-ink-tertiary">{label}</dt>
          <dd className="mt-0.5 text-body whitespace-pre-wrap text-ink wrap-anywhere">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

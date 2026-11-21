import { useCallback, useMemo, useState, type ReactNode } from "react"
import { matchPath, useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import type { ContextChip, UiContext } from "../../lib/assistant"
import { useApplication } from "../../lib/applications"
import { kitKeys, listProjects } from "../../lib/kitApi"
import { useOpportunity, useTodos } from "../../lib/opportunities"
import { PageContext, type ChipView } from "./pageContextState"

type Field = "opportunity_id" | "application_id" | "todo_id" | "project_id"

const KINDS: Record<Field, { key: string; label: string }> = {
  opportunity_id: { key: "opportunity", label: "Opportunity" },
  application_id: { key: "application", label: "Application" },
  todo_id: { key: "todo", label: "To-do" },
  project_id: { key: "project", label: "Project" },
}

/** The record the current page or open sheet is about, if any. */
function openRecord(pathname: string, search: URLSearchParams): { field: Field; id: string } | null {
  const path = pathname.replace(/\/+$/, "") || "/"
  const byPath: [string, Field][] = [
    ["/opportunities/:id", "opportunity_id"],
    ["/applications/:id", "application_id"],
    ["/kit/projects/:id", "project_id"],
  ]
  for (const [pattern, field] of byPath) {
    const id = matchPath(pattern, path)?.params.id
    if (id) return { field, id: decodeURIComponent(id) }
  }
  const open = search.get("open")
  if (path === "/opportunities" && open) return { field: "opportunity_id", id: open }
  if (path === "/applications" && open) return { field: "application_id", id: open }
  if (path === "/calendar") {
    if (search.get("todo")) return { field: "todo_id", id: search.get("todo") as string }
    if (open) return { field: "application_id", id: open }
  }
  return null
}

function useRecordTitle(record: { field: Field; id: string } | null) {
  const opportunity = useOpportunity(record?.field === "opportunity_id" ? record.id : undefined)
  const application = useApplication(record?.field === "application_id" ? record.id : undefined)
  const todos = useTodos("all", record?.field === "todo_id")
  const projects = useQuery({ queryKey: kitKeys.projects, queryFn: listProjects, enabled: record?.field === "project_id" })
  if (!record) return undefined
  switch (record.field) {
    case "opportunity_id": return opportunity.data?.title
    case "application_id": return application.data?.title
    case "todo_id": return todos.data?.find((row) => row.id === record.id)?.title
    case "project_id": return projects.data?.find((row) => row.id === record.id)?.name
  }
}

type Choice = "off" | "dismissed" | "added"
const NONE: Record<string, Choice> = {}

/** Suggests what the member is looking at as chips they can keep, drop or dismiss before asking. */
export function PageContextProvider({ children }: { children: ReactNode }) {
  const { pathname, search } = useLocation()
  const pageKey = pathname + search
  const record = useMemo(() => openRecord(pathname, new URLSearchParams(search)), [pathname, search])
  const title = useRecordTitle(record)
  const [state, setState] = useState<{ key: string; choices: Record<string, Choice>; selection: string | null }>({ key: pageKey, choices: {}, selection: null })
  // Choices belong to one page; a new page starts fresh without a frame of the old ones.
  const fresh = state.key === pageKey
  const choices = fresh ? state.choices : NONE
  const selection = fresh ? state.selection : null
  if (!fresh) setState({ key: pageKey, choices: {}, selection: null })

  const chips = useMemo<ChipView[]>(() => {
    const list: ChipView[] = []
    if (record) {
      const kind = KINDS[record.field]
      list.push({ ...kind, detail: title, added: choices[kind.key] !== "off" })
    }
    if (selection) {
      list.push({ key: "selection", label: "Selection", detail: selection.length > 80 ? `${selection.slice(0, 80)}…` : selection, added: choices.selection !== "off" })
    }
    return list.filter((chip) => choices[chip.key] !== "dismissed")
  }, [record, title, choices, selection])

  const patch = useCallback((change: (prev: { choices: Record<string, Choice>; selection: string | null }) => { choices: Record<string, Choice>; selection: string | null }) => setState((prev) => {
    const base = prev.key === pageKey ? prev : { key: pageKey, choices: {}, selection: null }
    return { key: pageKey, ...change(base) }
  }), [pageKey])
  const toggle = useCallback((key: string) => patch((prev) => ({ ...prev, choices: { ...prev.choices, [key]: prev.choices[key] === "off" ? "added" : "off" } })), [patch])
  const dismiss = useCallback((key: string) => patch((prev) => ({ ...prev, choices: { ...prev.choices, [key]: "dismissed" } })), [patch])
  const attachSelection = useCallback((text: string) => patch((prev) => ({ selection: text.slice(0, 5000), choices: { ...prev.choices, selection: "added" } })), [patch])

  const take = useCallback((): UiContext | undefined => {
    const added = chips.filter((chip) => chip.added)
    if (!added.length) return undefined
    const context: UiContext = {
      page: pageKey.slice(0, 300),
      chips: added.map(({ key, label, detail }): ContextChip => ({ key, label, ...(detail ? { detail: detail.slice(0, 200) } : {}) })),
    }
    if (record && added.some((chip) => chip.key === KINDS[record.field].key)) context[record.field] = record.id
    if (selection && added.some((chip) => chip.key === "selection")) context.selection = selection
    if (selection) patch((prev) => ({ ...prev, selection: null }))
    return context
  }, [chips, pageKey, record, selection, patch])

  const value = useMemo(() => ({ chips, toggle, dismiss, attachSelection, take, hasRecord: !!record }), [chips, toggle, dismiss, attachSelection, take, record])
  return <PageContext.Provider value={value}>{children}</PageContext.Provider>
}

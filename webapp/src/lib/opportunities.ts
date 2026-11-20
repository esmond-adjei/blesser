/** Opportunity catalogue, to-dos and calendar hooks, plus labels and calendar links. */
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { CountdownProps } from "@blesser/ui"
import * as api from "./api"
import type {
  Opportunity,
  OpportunityCategory,
  OpportunityKind,
  OpportunityQuery,
  Todo,
  TodoCreate,
  TodoUpdate,
} from "./types"

export const CATEGORY_LABELS: Record<OpportunityCategory, string> = {
  startup: "Startups",
  research: "Researchers",
  student: "Students",
}

export const KIND_LABELS: Record<OpportunityKind, string> = {
  grant: "Grant",
  fellowship: "Fellowship",
  scholarship: "Scholarship",
  accelerator: "Accelerator",
  incubator: "Incubator",
  competition: "Competition",
  internship: "Internship",
  call_for_proposals: "Call for proposals",
  training: "Training",
  conference: "Conference",
  job: "Job",
  other: "Other",
}

export const CATEGORIES = Object.keys(CATEGORY_LABELS) as OpportunityCategory[]
export const KINDS = Object.keys(KIND_LABELS) as OpportunityKind[]

export function isCategory(value: string): value is OpportunityCategory {
  return (CATEGORIES as string[]).includes(value)
}

export function isKind(value: string): value is OpportunityKind {
  return (KINDS as string[]).includes(value)
}

/** "Closes today", "12 days left", "Rolling", "Closed". */
export function deadlineLabel(opp: Pick<Opportunity, "rolling" | "days_left" | "deadline" | "is_open">): string {
  if (opp.rolling) return "Rolling"
  if (opp.days_left === null) return opp.deadline ? opp.deadline : "No deadline listed"
  if (!opp.is_open || opp.days_left < 0) return "Closed"
  if (opp.days_left === 0) return "Closes today"
  if (opp.days_left === 1) return "1 day left"
  return `${opp.days_left} days left`
}

/** Countdown props for an opportunity's deadline. */
export function countdownFor(
  opp: Pick<Opportunity, "rolling" | "days_left" | "deadline" | "deadline_date" | "is_open">,
): CountdownProps {
  if (opp.rolling) return { rolling: true }
  const closed = !opp.is_open || (opp.days_left !== null && opp.days_left < 0)
  return { daysLeft: closed ? -1 : opp.days_left, date: opp.deadline_date, label: opp.deadline || undefined }
}

/** yyyy-mm-dd plus one day, as yyyymmdd (all-day events end the next day). */
function nextDayCompact(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  const next = new Date(Date.UTC(y, m - 1, d + 1))
  return next.toISOString().slice(0, 10).replaceAll("-", "")
}

/** Google Calendar "add event" link for the deadline; null without a date. */
export function googleCalendarUrl(opp: Opportunity): string | null {
  if (!opp.deadline_date) return null
  const start = opp.deadline_date.replaceAll("-", "")
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: `Deadline: ${opp.title}${opp.organization ? ` (${opp.organization})` : ""}`,
    dates: `${start}/${nextDayCompact(opp.deadline_date)}`,
    details: [opp.summary, opp.link || opp.source_url].filter(Boolean).join("\n\n"),
  })
  return `https://calendar.google.com/calendar/render?${params.toString()}`
}

const PAGE = 24

export function useOpportunities(query: Omit<OpportunityQuery, "limit" | "offset">) {
  return useInfiniteQuery({
    queryKey: ["opportunities", query],
    queryFn: ({ pageParam }) => api.listOpportunities({ ...query, limit: PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, page) => n + page.items.length, 0)
      return loaded < last.total ? loaded : undefined
    },
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
}

export function useOpportunity(id: string | undefined) {
  return useQuery({
    queryKey: ["opportunity", id],
    queryFn: () => api.getOpportunity(id as string),
    enabled: !!id,
    staleTime: 60_000,
  })
}

export function useOpportunityFacets() {
  return useQuery({ queryKey: ["opportunities", "facets"], queryFn: api.opportunityFacets, staleTime: 60_000 })
}

/** {opportunity_id: application_id}. */
export function useTrackedOpportunities() {
  return useQuery({ queryKey: ["opportunities", "tracked"], queryFn: api.trackedOpportunities, staleTime: 30_000 })
}

export function useTrackOpportunity() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.trackOpportunity,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["opportunities", "tracked"] })
      void client.invalidateQueries({ queryKey: ["applications"] })
    },
  })
}

export function useTodos(status: "open" | "done" | "all" = "open", enabled = true) {
  return useQuery({ queryKey: ["todos", status], queryFn: () => api.listTodos(status), enabled })
}

export function useTodoMutations() {
  const client = useQueryClient()
  const refresh = () => void client.invalidateQueries({ queryKey: ["todos"] })
  const create = useMutation({ mutationFn: (body: TodoCreate) => api.createTodo(body), onSuccess: refresh })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: TodoUpdate }) => api.updateTodo(id, body),
    // Optimistic tick: the row moves at once; the refetch settles order.
    onMutate: async ({ id, body }) => {
      await client.cancelQueries({ queryKey: ["todos"] })
      const snapshots = client.getQueriesData<Todo[]>({ queryKey: ["todos"] })
      for (const [key, rows] of snapshots) {
        if (rows) client.setQueryData<Todo[]>(key, rows.map((t) => (t.id === id ? { ...t, ...body } as Todo : t)))
      }
      return { snapshots }
    },
    onError: (_err, _vars, context) => {
      for (const [key, rows] of context?.snapshots ?? []) client.setQueryData(key, rows)
    },
    onSettled: refresh,
  })
  const remove = useMutation({ mutationFn: (id: string) => api.deleteTodo(id), onSuccess: refresh })
  return { create, update, remove }
}

export function useCalendarFeed(enabled: boolean) {
  return useQuery({ queryKey: ["calendar-feed"], queryFn: api.getCalendarFeed, enabled, staleTime: Infinity })
}

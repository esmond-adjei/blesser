import * as React from "react"
import { useExportPdf } from "../../lib/exportPdf"
import { useQueryClient } from "@tanstack/react-query"
import * as api from "../../lib/api"
import { hasDraft } from "../../lib/drafts"
import { toastError } from "../../lib/toast"
import { useRunCandidates } from "../../lib/queries"
import { useUrlParam } from "../../lib/urlParams"
import type { ListParams, SkippedItem } from "../../lib/types"
import { FileDown, MailPlus, ThumbsDown, ThumbsUp, X } from "lucide-react"
import { professorPlace } from "../../lib/entities"
import { Avatar } from "../ui/avatar"
import { Alert, AlertDescription } from "../ui/feedback"
import { Input } from "../ui/input"
import { Select } from "../ui/select"
import { CandidateStatusBadge, ScoreBar } from "../ui/status"
import { CandidateRowMenu } from "../dossier/CandidateRowMenu"
import { EntityList, EntityRow, EntityRowSkeleton, ROW_MENU_POSITION } from "../entity/EntityRow"
import { EmptyState } from "../feedback/EmptyState"
import { DEFAULT_PAGE_SIZE, Pager } from "./Pager"

const PAGE_SIZE = DEFAULT_PAGE_SIZE

export function CandidatesTab({ runId, fallbackPoll }: { runId: string; fallbackPoll: number | false }) {
  const qc = useQueryClient()
  // Rail filters live in the URL (c-prefixed: the run page itself uses
  // ?tab= and ?status=) so they are shareable and survive rail toggles.
  const [status, setStatusState] = useUrlParam("cstatus", "all")
  const [sort, setSortState] = useUrlParam("csort", "score")
  const [offset, setOffset] = React.useState(0)
  const [query, setQuery] = useUrlParam("cq")
  const [selected, setSelected] = React.useState<Set<string>>(new Set())
  const [bulkBusy, setBulkBusy] = React.useState<string | null>(null)
  const [bulkMsg, setBulkMsg] = React.useState<{ ok: string; skipped: SkippedItem[] } | null>(null)
  const { exporting, exportPdf } = useExportPdf()

  const params: ListParams = React.useMemo(
    () => ({ status, sort, limit: PAGE_SIZE, offset }),
    [status, sort, offset],
  )
  const { data, isLoading, isFetching } = useRunCandidates(runId, params, fallbackPoll)
  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const page = Math.floor(offset / PAGE_SIZE)

  function resetPage(next: { status?: string; sort?: string }) {
    if (next.status !== undefined) setStatusState(next.status)
    if (next.sort !== undefined) setSortState(next.sort)
    setOffset(0)
  }

  const q = query.trim().toLowerCase()
  const visible = q
    ? items.filter((c) =>
        `${c.professor_name} ${c.school_name} ${c.program_name}`.toLowerCase().includes(q),
      )
    : items

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allVisibleSelected = visible.length > 0 && visible.every((c) => selected.has(c.id))

  function selectAllVisible() {
    setSelected((prev) => new Set([...prev, ...visible.map((c) => c.id)]))
  }

  async function refreshAll() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["candidates", runId] }),
      qc.invalidateQueries({ queryKey: ["drafts", runId] }),
      qc.invalidateQueries({ queryKey: ["tasks", runId] }),
    ])
  }

  async function bulk(action: "drafts" | "approve" | "reject", fn: () => Promise<{ skipped: SkippedItem[]; done: number; label: string }>) {
    setBulkBusy(action)
    setBulkMsg(null)
    try {
      const res = await fn()
      setBulkMsg({ ok: `${res.label}: ${res.done} succeeded.`, skipped: res.skipped })
      setSelected(new Set())
      await refreshAll()
    } catch (e) {
      toastError(e)
    } finally {
      setBulkBusy(null)
    }
  }

  const ids = [...selected]
  const onBulkDrafts = () =>
    bulk("drafts", async () => {
      // Only page-visible rows with a finished draft are skipped locally; the
      // server's `skipped` covers off-page rows, including drafts in progress.
      const byId = new Map(items.map((c) => [c.id, c]))
      const clientSkipped: SkippedItem[] = []
      const toQueue: string[] = []
      for (const id of ids) {
        const row = byId.get(id)
        if (row && hasDraft(row)) clientSkipped.push({ id, reason: "already has a draft" })
        else toQueue.push(id)
      }
      if (toQueue.length === 0)
        return { skipped: clientSkipped, done: 0, label: "Draft requests queued" }
      const r = await api.requestDrafts(runId, toQueue)
      return {
        skipped: [...clientSkipped, ...r.skipped],
        done: r.queued.length,
        label: "Draft requests queued",
      }
    })
  const onBulkReview = (approved: boolean) =>
    bulk(approved ? "approve" : "reject", async () => {
      const r = await api.reviewBulk(
        runId,
        ids.map((candidate_id) => ({ candidate_id, approved })),
      )
      return { skipped: r.skipped, done: r.updated.length, label: approved ? "Approved" : "Rejected" }
    })

  if (isLoading) return <div aria-label="Loading candidates" aria-busy="true">{Array.from({ length: 3 }, (_, i) => <EntityRowSkeleton key={i} />)}</div>
  if (total === 0 && status === "all" && !q)
    return (
      <EmptyState
        mascot="reading"
        title="No candidates yet"
        description="Professors land here once they're scored against your interests. Follow along under Agent tasks."
      />
    )

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Input
          placeholder="Search this page"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="h-8 min-w-0 flex-1 text-xs"
        />
        <Select value={status} onChange={(e) => resetPage({ status: e.target.value })} className="h-8 w-auto text-xs" aria-label="Status">
          <option value="all">All</option>
          <option value="scored">Scored</option>
          <option value="drafted">Drafted</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </Select>
        <Select value={sort} onChange={(e) => resetPage({ sort: e.target.value })} className="h-8 w-auto text-xs" aria-label="Sort">
          <option value="score">Best fit</option>
          <option value="recent">Newest</option>
        </Select>
      </div>

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 rounded-xl bg-primary py-1.5 pr-1.5 pl-3 text-xs font-semibold text-primary-foreground">
          <span className="mr-auto">{selected.size} selected</span>
          {[
            { key: "approve", label: "Approve", icon: ThumbsUp, run: () => void onBulkReview(true) },
            { key: "reject", label: "Reject", icon: ThumbsDown, run: () => void onBulkReview(false) },
            { key: "drafts", label: bulkBusy === "drafts" ? "Queueing…" : "Drafts", icon: MailPlus, run: () => void onBulkDrafts() },
            { key: "pdf", label: exporting ? "Exporting…" : "PDF", icon: FileDown, run: () => void exportPdf(ids) },
          ].map((a) => (
            <button
              key={a.key}
              type="button"
              disabled={bulkBusy !== null || (a.key === "pdf" && exporting)}
              onClick={a.run}
              className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md bg-primary-foreground/15 px-2 transition-colors hover:bg-primary-foreground/25 disabled:opacity-60"
            >
              <a.icon className="size-3.5" /> {a.label}
            </button>
          ))}
          <button
            type="button"
            data-tooltip={allVisibleSelected ? "Unselect every row" : "Select every row on this page"}
            onClick={allVisibleSelected ? () => setSelected(new Set()) : selectAllVisible}
            className="inline-flex h-7 cursor-pointer items-center rounded-md px-2 hover:bg-primary-foreground/15"
          >
            {allVisibleSelected ? "None" : "All"}
          </button>
          <button
            type="button"
            aria-label="Clear selection"
            onClick={() => setSelected(new Set())}
            className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md hover:bg-primary-foreground/15"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}
      {bulkMsg && (
        <Alert>
          <AlertDescription>
            {bulkMsg.ok}
            {bulkMsg.skipped.length > 0 && (
              <> Skipped: {bulkMsg.skipped.map((s) => `${s.id.slice(0, 8)} (${s.reason})`).join(", ")}</>
            )}
          </AlertDescription>
        </Alert>
      )}
      {visible.length === 0 ? (
        <p className="type-meta">Nothing on this page matches.</p>
      ) : (
        <EntityList>
          {visible.map((c) => (
            <EntityRow
              key={c.id}
              to={`/dossier/${c.id}`}
              selected={selected.has(c.id)}
              onSelect={() => toggleSelect(c.id)}
              label={c.professor_name}
              leading={<Avatar name={c.professor_name} src={c.professor_photo_url} size="sm" />}
              title={c.professor_name}
              subtitle={professorPlace(c.program_name, c.school_name)}
              end={
                <>
                  <CandidateStatusBadge status={c.status} quiet />
                  <ScoreBar score={c.similarity_score} />
                </>
              }
              menu={<CandidateRowMenu candidate={c} runId={runId} isActive={false} className={ROW_MENU_POSITION} />}
            />
          ))}
        </EntityList>
      )}
      {isFetching && <span className="type-caption">Refreshing…</span>}

      <Pager page={page} pages={pages} total={total} pageSize={PAGE_SIZE} onPage={(p) => setOffset(p * PAGE_SIZE)} />
    </div>
  )
}

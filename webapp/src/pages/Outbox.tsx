import * as React from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { useOutboxDrafts, useRuns } from "../lib/queries"
import { runTitle } from "../lib/format"
import { usePreviewParam, useUrlParam } from "../lib/urlParams"
import { buttonVariants } from "../components/ui/button"
import { Alert, AlertDescription } from "../components/ui/feedback"
import { HealthBanner } from "../components/layout/AppShell"
import { useDetailPanel } from "../components/layout/DetailPanel"
import { EmptyState } from "../components/feedback/EmptyState"
import { Avatar } from "../components/ui/avatar"
import { EntityList, EntityRow, ROW_MENU_POSITION } from "../components/entity/EntityRow"
import { OutboxDetailPanel } from "../components/outbox/OutboxDetailPanel"
import { DraftPreviewActions } from "../components/layout/PreviewActions"
import { DraftRowMenu } from "../components/outbox/DraftRowMenu"
import { CandidateStatusBadge } from "../components/ui/status"
import { ListingView, type ListingStatus } from "../components/listing/ListingView"

/** Unsent drafts across runs. Drafts load per run; the rail panel is keyed by draft id. */
export function Outbox() {
  const { data: runs } = useRuns()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // Filter state lives in the URL (?q=, ?run=) so it is shareable.
  const [query, setQuery] = useUrlParam("q")
  // Sort order lives in the URL (?sort=). Newest first matches the API's ordering.
  const [sortParam, setSortParam] = useUrlParam("sort", "newest")
  const sort =
    sortParam === "score" || sortParam === "subject" || sortParam === "professor"
      ? sortParam
      : "newest"
  const scopeParam = searchParams.get("run") ?? "all"
  const scope =
    scopeParam === "all" || (runs?.some((run) => run.id === scopeParam) ?? false)
      ? scopeParam
      : "all"
  const { items, isLoading, isError, refetch } = useOutboxDrafts()
  const { setPanel, clearPanel } = useDetailPanel()
  const { previewId, openPreview: openDraft, closePreview: closeDraft } = usePreviewParam()

  const selectedId = previewId
  // Effect deps are the cached draft object plus strings; the wrapper objects
  // are rebuilt every render and would retrigger the effect forever.
  const match = selectedId ? items.find((i) => i.draft.id === selectedId) : undefined
  const selectedDraft = match?.draft ?? null
  const selectedRunId = match?.runId ?? null
  const selectedRunTitle = match?.runTitle ?? null

  // Selection lives in ?preview= so the rail is deep-linkable and Back closes it.
  const scoped = scope === "all" ? items : items.filter((i) => i.runId === scope)
  const q = query.trim().toLowerCase()
  const matched = q
    ? scoped.filter((i) =>
        `${i.draft.professor_name} ${i.draft.subject} ${i.draft.body}`.toLowerCase().includes(q),
      )
    : scoped
  // Client-side ordering; null scores sink below scored rows.
  const filtered = [...matched].sort((a, b) => {
    if (sort === "score") return (b.draft.similarity_score ?? -1) - (a.draft.similarity_score ?? -1)
    if (sort === "subject") return a.draft.subject.localeCompare(b.draft.subject)
    if (sort === "professor") return a.draft.professor_name.localeCompare(b.draft.professor_name)
    return +new Date(b.draft.created_at) - +new Date(a.draft.created_at)
  })

  // Unmount cleanup is its own effect: clearing here would flash the rail after edits.
  React.useEffect(() => {
    if (selectedDraft && selectedRunId && selectedRunTitle) {
      setPanel(
        <OutboxDetailPanel
          key={selectedDraft.id}
          draft={selectedDraft}
          runId={selectedRunId}
          runTitle={selectedRunTitle}
        />,
        {
          onClose: closeDraft,
          title: selectedDraft.subject || "Draft",
          ref: { kind: "draft", id: selectedDraft.id },
          actions: <DraftPreviewActions draftId={selectedDraft.id} runId={selectedRunId} />,
        },
      )
    } else {
      clearPanel()
    }
  }, [selectedDraft, selectedRunId, selectedRunTitle, setPanel, clearPanel, closeDraft])

  React.useEffect(() => () => clearPanel(), [clearPanel])

  if (!runs || runs.length === 0) {
    return (
      <div className="space-y-4">
        <HealthBanner />
        <EmptyState
          mascot="reading"
          title="No runs yet"
          description="Drafts are written against researched professors. Start a run first."
          action={
            <Link to="/new" className={buttonVariants({ size: "sm" })}>
              New run
            </Link>
          }
        />
      </div>
    )
  }

  const status: ListingStatus = isLoading
    ? "loading"
    : isError
      ? "error"
      : items.length === 0
        ? "empty"
        : "ready"

  return (
    <ListingView
      title="Outbox"
      search={{ value: query, onChange: setQuery, placeholder: "Search drafts..." }}
      filters={[
        {
          id: "run",
          label: "Run",
          value: scope,
          options: [
            { value: "all", label: "All runs" },
            ...(runs ?? []).map((run) => ({
              value: run.id,
              label: runTitle(run),
            })),
          ],
          onChange: (next) => {
            const search = new URLSearchParams(searchParams)
            if (next === "all") search.delete("run")
            else search.set("run", next)
            search.delete("q")
            navigate({ pathname: "/outbox", search: search.toString() }, { replace: true })
          },
        },
      ]}
      viewStorageKey="outbox:view"
      availableViews={["list"]}
      sort={{
        value: sort,
        options: [
          { value: "newest", label: "Newest first" },
          { value: "professor", label: "Professor A–Z" },
          { value: "score", label: "Top score" },
          { value: "subject", label: "Subject A–Z" },
        ],
        onChange: setSortParam,
      }}
      items={filtered}
      renderItems={() => (
        <EntityList>
          {filtered.map(({ draft: d, runId, runTitle: scopeTitle }) => {
            const active = d.id === selectedId
            return (
              <EntityRow
                key={d.id}
                active={active}
                onClick={() => openDraft(d.id)}
                label={`Draft to ${d.professor_name}`}
                leading={<Avatar name={d.professor_name} src={d.professor_photo_url} size="sm" />}
                title={d.professor_name}
                subtitle={d.subject || "(no subject)"}
                end={
                  <>
                    <CandidateStatusBadge status={d.candidate_status === "drafted" ? "scored" : d.candidate_status} quiet />
                    <span className="text-xs whitespace-nowrap text-muted-foreground" data-tooltip={scopeTitle}>
                      {new Date(d.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                    </span>
                  </>
                }
                menu={<DraftRowMenu draft={d} runId={runId} isActive={active} className={ROW_MENU_POSITION} />}
              />
            )
          })}
        </EntityList>
      )}
      status={status}
      errorText="Couldn't load drafts."
      onRetry={() => void refetch()}
      empty={
        <EmptyState
          mascot="empty-box"
          title="Outbox is empty"
          description="Request a draft from any scored candidate. Drafts are never sent. Approving only marks them reviewed, so copy it into your own mail client."
          action={
            <Link to="/dossier" className={buttonVariants({ size: "sm", variant: "outline" })}>
              Browse matches
            </Link>
          }
        />
      }
      notice={
        selectedId && !isLoading && !selectedDraft ? (
          <Alert variant="destructive">
            <AlertDescription>
              Draft not found. It may have been discarded. Pick another one below.
            </AlertDescription>
          </Alert>
        ) : undefined
      }
    />
  )
}

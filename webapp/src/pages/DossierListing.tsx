import * as React from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { useCandidateSearch, useRuns } from "../lib/queries"
import { runTitle } from "../lib/format"
import { usePreviewParam, useSetUrlParam, useUrlParam } from "../lib/urlParams"
import { FileDown, ListChecks, Loader2, Plus } from "lucide-react"
import { useExportPdf } from "../lib/exportPdf"
import { Button, buttonVariants } from "../components/ui/button"
import { AddProfessorDialog } from "../components/dialogs/ProspectDialogs"
import { toastSuccess } from "../lib/toast"
import { HealthBanner } from "../components/layout/AppShell"
import { useDetailPanel } from "../components/layout/DetailPanel"
import { CandidateStatusBadge, ScoreBar } from "../components/ui/status"
import { EmptyState } from "../components/feedback/EmptyState"
import { Avatar } from "../components/ui/avatar"
import { EntityList, EntityRow, ROW_MENU_POSITION } from "../components/entity/EntityRow"
import { professorPlace } from "../lib/entities"
import { DossierDetailPanel } from "../components/dossier/DossierDetailPanel"
import { CandidatePreviewActions } from "../components/layout/PreviewActions"
import { CandidateRowMenu } from "../components/dossier/CandidateRowMenu"
import { OtherMatches, ProfessorCard } from "../components/dossier/ProfessorCard"
import { ListingView, gridColumnsClass, type ListingStatus } from "../components/listing/ListingView"

/** Professor profiles across a run scope, served by the candidate search endpoint. */
export function DossierListingPage() {
  const { data: runs } = useRuns()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // Bumped per open so the dialog remounts with fresh fields.
  const [adding, setAdding] = React.useState(0)
  // Select mode picks professors for one PDF instead of opening them.
  const [picked, setPicked] = React.useState<Set<string> | null>(null)
  const selecting = picked !== null
  const { exporting, exportPdf } = useExportPdf()
  const togglePick = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev ?? [])
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const setParam = useSetUrlParam()
  // Filter state lives in the URL (?q=, ?run=) so it is shareable.
  const query = searchParams.get("q") ?? ""
  const setQuery = (next: string) => setParam("q", next)
  // Sort order lives in the URL too (?sort=); unknown values fall back to ranking.
  const [sortParam, setSortParam] = useUrlParam("sort", "score")
  const sort = sortParam === "name" || sortParam === "school" ? sortParam : "score"
  // Scope is a run id or "all"; unknown or still-loading runs fall back to the first.
  const runParam = searchParams.get("run")
  const scope =
    runParam === "all" || (runs?.some((run) => run.id === runParam) ?? false)
      ? runParam
      : (runs && runs.length > 0 ? runs[0].id : null)

  const isAll = scope === "all"
  // One server search serves both scopes: the run filter becomes run_ids.
  const search = useCandidateSearch(
    {
      status: "all",
      sort: "score",
      limit: 200,
      offset: 0,
      q: query.trim() || undefined,
      run_ids: isAll || scope === null ? undefined : [scope],
    },
    scope !== null,
  )
  const titles = React.useMemo(
    () => new Map((runs ?? []).map((run) => [run.id, runTitle(run)])),
    [runs],
  )
  const scoped = (search.data?.items ?? []).map((candidate) => ({
    candidate,
    runId: candidate.run_id,
    runTitle: titles.get(candidate.run_id) ?? "",
  }))
  // One entry per professor, led by its best match (the feed is score-ranked).
  const byProfessor = new Map<string, (typeof scoped)[number] & { matchIds: string[] }>()
  for (const entry of scoped) {
    const lead = byProfessor.get(entry.candidate.professor_id)
    if (lead) lead.matchIds.push(entry.candidate.id)
    else byProfessor.set(entry.candidate.professor_id, { ...entry, matchIds: [entry.candidate.id] })
  }
  const grouped = [...byProfessor.values()]
  const isLoading = search.isLoading
  const isError = search.isError

  const sorted = [...grouped].sort((a, b) => {
    if (sort === "name") return a.candidate.professor_name.localeCompare(b.candidate.professor_name)
    if (sort === "school")
      return (
        a.candidate.school_name.localeCompare(b.candidate.school_name)
        || a.candidate.professor_name.localeCompare(b.candidate.professor_name)
      )
    return (b.candidate.similarity_score ?? -1) - (a.candidate.similarity_score ?? -1)
  })
  const bestId = [...scoped]
    .filter(({ candidate }) => candidate.similarity_score != null)
    .sort((a, b) => (b.candidate.similarity_score ?? 0) - (a.candidate.similarity_score ?? 0))[0]?.candidate.id

  const selectScope = (next: string) => {
    const search = new URLSearchParams(searchParams)
    search.set("run", next)
    search.delete("q")
    navigate({ pathname: "/dossier", search: search.toString() }, { replace: true })
  }

  // Selection lives in ?preview= so the rail is deep-linkable and Back closes it.
  const { previewId: selectedId, openPreview: openCandidate, closePreview: closeCandidate } = usePreviewParam()
  const { setPanel, clearPanel } = useDetailPanel()

  // The rail appears only after a row is picked. Deps are plain strings: the
  // row wrapper is rebuilt every render and must not feed the effect.
  const selected = scoped.find(({ candidate }) => candidate.id === selectedId) ?? null
  const selectedRunId = selected?.runId ?? null
  const selectedName = selected?.candidate.professor_name ?? null
  React.useEffect(() => {
    if (selectedId && selectedRunId) {
      setPanel(
        <DossierDetailPanel key={selectedId} candidateId={selectedId} />,
        {
          onClose: closeCandidate,
          title: selectedName ?? "Details",
          ref: { kind: "candidate", id: selectedId },
          actions: <CandidatePreviewActions candidateId={selectedId} />,
        },
      )
    } else {
      clearPanel()
    }
  }, [selectedId, selectedRunId, selectedName, setPanel, clearPanel, closeCandidate])

  // Unmount only: clearing in the effect above would reopen the rail on every refetch.
  React.useEffect(() => () => clearPanel(), [clearPanel])

  if (scope === null || (runs ?? []).length === 0) {
    return (
      <div className="space-y-4">
        <HealthBanner />
        <EmptyState
          mascot="reading"
          title="No runs yet"
          description="Matches come from researched professors. Start a run first."
          action={<Link to="/new" className={buttonVariants({ size: "sm" })}>New run</Link>}
        />
      </div>
    )
  }

  // The chosen run scope goes first, so "add" defaults to where you are.
  const runOptions = (runs ?? [])
    .map((r) => ({ id: r.id, label: runTitle(r) }))
    .sort((a, b) => (a.id === scope ? -1 : b.id === scope ? 1 : 0))
  const addButton = (
    <Button aria-label="Add a professor" size="sm" onClick={() => setAdding((n) => n + 1)}>
      <Plus />
    </Button>
  )
  const headerActions = selecting ? (
    <Button size="sm" variant="ghost" onClick={() => setPicked(null)}>
      Done
    </Button>
  ) : (
    <>
      {sorted.length > 0 && (
        <Button size="sm" variant="outline" onClick={() => setPicked(new Set())} data-tooltip="Pick professors to export as one PDF">
          <ListChecks /> Select
        </Button>
      )}
      {addButton}
    </>
  )
  const pickedIds = [...(picked ?? [])].filter((id) => sorted.some(({ candidate }) => candidate.id === id))
  const selectionBar = selecting && (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-2">
      <span className="px-1 text-sm font-medium">{pickedIds.length} selected</span>
      <Button
        size="sm"
        variant="outline"
        onClick={() =>
          setPicked(
            sorted.length > 0 && pickedIds.length === sorted.length
              ? new Set()
              : new Set(sorted.map(({ candidate }) => candidate.id)),
          )
        }
      >
        {sorted.length > 0 && pickedIds.length === sorted.length ? "Unselect all" : `Select all ${sorted.length}`}
      </Button>
      {pickedIds.length > 0 && pickedIds.length < sorted.length && (
        <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>
          Clear
        </Button>
      )}
      <Button data-tooltip="Download the selected professors as one PDF"
        size="sm"
        className="ml-auto"
        disabled={pickedIds.length === 0 || exporting}
        onClick={() => void exportPdf(pickedIds)}
      >
        {exporting ? <Loader2 className="animate-spin" /> : <FileDown />}
        {exporting ? "Exporting…" : pickedIds.length > 1 ? `Export ${pickedIds.length} as one PDF` : "Export PDF"}
      </Button>
    </div>
  )

  const status: ListingStatus = isLoading
    ? "loading"
    : isError
      ? "error"
      : scoped.length === 0
        ? "empty"
        : "ready"

  return (
    <>
    <ListingView
      title="Matches"
      search={{ value: query, onChange: setQuery, placeholder: "Search professors…" }}
      filters={[
        {
          id: "run",
          label: "Run",
          value: scope,
          options: [
            { value: "all", label: "All" },
            ...(runs ?? []).map((run) => ({
              value: run.id,
              label: runTitle(run),
            })),
          ],
          onChange: selectScope,
        },
      ]}
      viewStorageKey="dossier:view"
      availableViews={["list", "grid"]}
      gridColumns={2}
      sort={{
        value: sort,
        options: [
          { value: "score", label: "Top score" },
          { value: "name", label: "Name A–Z" },
          { value: "school", label: "School A–Z" },
        ],
        onChange: setSortParam,
      }}
      items={sorted}
      renderItems={(view, { columns }) => {
        if (view === "grid") {
          return (
            <ul className={`grid gap-3 ${gridColumnsClass(columns)}`}>
              {sorted.map(({ candidate, runId, matchIds }) => (
                <ProfessorCard
                  key={candidate.id}
                  candidate={candidate}
                  runId={runId}
                  otherMatches={matchIds.length - 1}
                  isBest={candidate.id === bestId}
                  isActive={selectedId !== null && matchIds.includes(selectedId)}
                  onOpen={() => (selecting ? togglePick(candidate.id) : openCandidate(candidate.id))}
                  selected={selecting ? picked.has(candidate.id) : undefined}
                />
              ))}
            </ul>
          )
        }
        return (
          <EntityList>
            {sorted.map(({ candidate, runId, runTitle: scopeTitle, matchIds }) => {
              const active = selectedId !== null && matchIds.includes(selectedId)
              const isPicked = selecting && picked.has(candidate.id)
              return (
                <EntityRow
                  key={candidate.id}
                  active={selecting ? isPicked : active}
                  onClick={() => (selecting ? togglePick(candidate.id) : openCandidate(candidate.id))}
                  selected={selecting ? isPicked : undefined}
                  onSelect={selecting ? () => togglePick(candidate.id) : undefined}
                  label={candidate.professor_name}
                  leading={<Avatar name={candidate.professor_name} src={candidate.professor_photo_url} size="sm" />}
                  title={candidate.professor_name}
                  subtitle={isAll ? `${professorPlace(candidate.program_name, candidate.school_name)}, ${scopeTitle}` : professorPlace(candidate.program_name, candidate.school_name)}
                  end={
                    <>
                      {candidate.id === bestId && <span className="g-best">Best fit</span>}
                      <CandidateStatusBadge status={candidate.status} quiet />
                      <OtherMatches count={matchIds.length - 1} />
                      <ScoreBar score={candidate.similarity_score} />
                    </>
                  }
                  menu={selecting ? undefined : <CandidateRowMenu candidate={candidate} runId={runId} isActive={active} className={ROW_MENU_POSITION} />}
                />
              )
            })}
          </EntityList>
        )
      }}
      status={status}
      errorText={`Couldn't load matches${isAll ? " across runs" : " for this run"}.`}
      onRetry={() => void search.refetch()}
      empty={
        <EmptyState
          mascot="empty-box"
          title="No professors yet"
          description="Profiles appear as professors get scored in this run. Follow along on the run's review page."
          action={
            <span className="flex flex-wrap justify-center gap-2">
              {addButton}
              {!isAll && scope && (
                <Link to={`/runs/${scope}`} className={buttonVariants({ size: "sm", variant: "outline" })}>Open run workspace</Link>
              )}
            </span>
          }
        />
      }
      actions={headerActions}
      notice={selectionBar || undefined}
    />
    {adding > 0 && (
      <AddProfessorDialog
        key={adding}
        runOptions={runOptions}
        open
        onOpenChange={(o) => { if (!o) setAdding(0) }}
        onCreated={(p) => toastSuccess(`Researching ${p.name}. They'll appear in Matches once scored.`)}
      />
    )}
    </>
  )
}

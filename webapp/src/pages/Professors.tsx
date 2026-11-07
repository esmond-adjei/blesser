import * as React from "react"
import { useProfessors } from "../lib/queries"
import { useUrlParam } from "../lib/urlParams"
import type { FacultyRow } from "../lib/types"
import { EmptyState } from "../components/feedback/EmptyState"
import { ListingView, type ListingStatus } from "../components/listing/ListingView"
import { MatchProfessorDialog } from "../components/dialogs/MatchProfessorDialog"
import { ProfessorCard } from "../components/cards/ProfessorCard"

export function Professors() {
  const { data, isLoading, isError, refetch } = useProfessors()
  const professors = React.useMemo(() => data ?? [], [data])
  const [query, setQuery] = useUrlParam("q")
  const [sortParam, setSortParam] = useUrlParam("sort", "name")
  const sort = sortParam === "fit" ? "fit" : "name"
  const [matchParam, setMatchParam] = useUrlParam("match", "all")
  const matchFilter = matchParam === "matched" || matchParam === "unmatched" ? matchParam : "all"
  const schools = React.useMemo(
    () => [...new Set(professors.map((p) => p.school).filter(Boolean))].sort((a, b) => a.localeCompare(b)),
    [professors],
  )
  const [schoolParam, setSchoolParam] = useUrlParam("school", "all")
  const schoolFilter = schools.includes(schoolParam) ? schoolParam : "all"
  const [checking, setChecking] = React.useState<FacultyRow | null>(null)

  const q = query.trim().toLowerCase()
  const shown = professors
    .filter((p) => {
      if (matchFilter !== "all" && !!p.candidate_id !== (matchFilter === "matched")) return false
      if (schoolFilter !== "all" && p.school !== schoolFilter) return false
      return !q || `${p.name} ${p.school} ${p.program} ${p.lab_name ?? ""}`.toLowerCase().includes(q)
    })
    .sort((a, b) =>
      sort === "fit"
        ? (b.similarity_score ?? -1) - (a.similarity_score ?? -1) || a.name.localeCompare(b.name)
        : a.name.localeCompare(b.name),
    )


  const status: ListingStatus = isLoading ? "loading" : isError ? "error" : professors.length === 0 ? "empty" : "ready"

  return (
    <>
      <ListingView
        title="Professors"
        search={{ value: query, onChange: setQuery, placeholder: "Search professors, schools, labs…" }}
        filters={[
          {
            id: "match",
            label: "Match",
            value: matchFilter,
            options: [
              { value: "all", label: "Everyone" },
              { value: "matched", label: "In your matches" },
              { value: "unmatched", label: "Not matched" },
            ],
            onChange: setMatchParam,
          },
          {
            id: "school",
            label: "School",
            value: schoolFilter,
            options: [{ value: "all", label: "All schools" }, ...schools.map((s) => ({ value: s, label: s }))],
            onChange: setSchoolParam,
          },
        ]}
        sort={{
          value: sort,
          options: [
            { value: "name", label: "Name A–Z" },
            { value: "fit", label: "Best fit" },
          ],
          onChange: setSortParam,
        }}
        viewStorageKey="professors:view"
        availableViews={["grid"]}
        items={shown}
        renderItems={() => (
          <ul className="grid gap-3 lg:grid-cols-2">
            {shown.map((p) => (
              <ProfessorCard key={p.id} professor={p} onCheck={() => setChecking(p)} />
            ))}
          </ul>
        )}
        status={status}
        errorText="Couldn't load professors."
        onRetry={() => void refetch()}
        noMatchText="Nothing matches these filters."
        empty={
          <EmptyState
            mascot="empty-box"
            title="No professors yet"
            description="Professors appear here as runs research schools, whether or not they match your interests."
          />
        }
      />
      {checking && (
        <MatchProfessorDialog professor={checking} open onOpenChange={(o) => !o && setChecking(null)} />
      )}
    </>
  )
}

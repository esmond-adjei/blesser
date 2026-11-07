import * as React from "react"
import { Link } from "react-router-dom"
import { BookOpen, Users } from "lucide-react"
import { useApplications } from "../lib/applications"
import { useAllRunSchools, useRuns } from "../lib/queries"
import { runTitle } from "../lib/format"
import { schoolFacultyCount } from "../lib/schools"
import { useUrlParam } from "../lib/urlParams"
import { Plus } from "lucide-react"
import { Button, buttonVariants } from "../components/ui/button"
import { SchoolDialog } from "../components/dialogs/ProspectDialogs"
import { toastSuccess } from "../lib/toast"
import { EmptyState } from "../components/feedback/EmptyState"
import { EntityList, EntityRow, ROW_MENU_POSITION } from "../components/entity/EntityRow"
import { FactList } from "../components/entity/facts"
import { SchoolImage } from "../components/entity/SchoolImage"
import { ListingView, gridColumnsClass, type ListingStatus } from "../components/listing/ListingView"
import { SchoolCard, SchoolRowMenu } from "../components/schools/SchoolCard"
import { useOpenRecord } from "../components/layout/openRecord"
import { useDetailPanel } from "../components/layout/DetailPanel"
import { SCHOOL_TIERS } from "../components/run/runFormModel"

export function Schools() {
  const { data: runs } = useRuns()
  const { items, isLoading, isError, refetch } = useAllRunSchools()
  const { apps } = useApplications()
  const [query, setQuery] = useUrlParam("q")
  // Creating needs a run to own the school; without one, the empty state
  // routes to New run instead of offering a button that cannot succeed.
  const runOptions = (runs ?? []).map((r) => ({ id: r.id, label: runTitle(r) }))
  const [adding, setAdding] = React.useState(0)
  const canAdd = runOptions.length > 0
  const addButton = canAdd ? (
    <Button aria-label="Add a school" size="sm" onClick={() => setAdding((n) => n + 1)}>
      <Plus />
    </Button>
  ) : undefined
  // Sort order lives in the URL (?sort=); unknown values fall back to name.
  const [sortParam, setSortParam] = useUrlParam("sort", "name")
  const sort = sortParam === "programmes" || sortParam === "faculty" ? sortParam : "name"

  // Filters live in the URL so they are shareable; unknown values fall back to "all".
  const [runParam, setRunParam] = useUrlParam("run", "all")
  const runFilter = runParam === "all" || (runs?.some((r) => r.id === runParam) ?? false) ? runParam : "all"
  const countries = React.useMemo(() => {
    const set = new Set<string>()
    for (const { school } of items) set.add(school.country?.trim() || "Unknown")
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [items])
  const [countryParam, setCountryParam] = useUrlParam("country", "all")
  const countryFilter = countryParam === "all" || countries.includes(countryParam) ? countryParam : "all"
  // Tier discovery placed the school in; "none" = no tier.
  const [tierParam, setTierParam] = useUrlParam("tier", "all")
  const tierFilter = tierParam === "none" || SCHOOL_TIERS.some((t) => t.value === tierParam) ? tierParam : "all"
  const [trackedParam, setTrackedParam] = useUrlParam("tracked", "all")
  const trackedFilter = trackedParam === "tracked" || trackedParam === "untracked" ? trackedParam : "all"
  // Matched by normalized name, the same join the school detail page uses.
  const trackedNames = React.useMemo(() => {
    const set = new Set<string>()
    for (const a of apps) {
      const name = a.school.trim().toLowerCase()
      if (name) set.add(name)
    }
    return set
  }, [apps])

  const q = query.trim().toLowerCase()
  const filtered = items.filter(({ school, runIds, runTitle }) => {
    // A school belongs to every run that uses it.
    if (runFilter !== "all" && !runIds.includes(runFilter)) return false
    if (countryFilter !== "all" && (school.country?.trim() || "Unknown") !== countryFilter) return false
    if (tierFilter !== "all" && (school.tier ?? "none") !== tierFilter) return false
    if (trackedFilter !== "all") {
      const tracked = trackedNames.has(school.name.trim().toLowerCase())
      if (trackedFilter === "tracked" ? !tracked : tracked) return false
    }
    if (!q) return true
    return `${school.name} ${school.country ?? ""} ${runTitle} ${school.programs.map((p) => p.name).join(" ")}`.toLowerCase().includes(q)
  })
  const sorted = [...filtered].sort((a, b) => {
    if (sort === "programmes")
      return b.school.programs.length - a.school.programs.length || a.school.name.localeCompare(b.school.name)
    if (sort === "faculty")
      return schoolFacultyCount(b.school) - schoolFacultyCount(a.school) || a.school.name.localeCompare(b.school.name)
    return a.school.name.localeCompare(b.school.name)
  })

  // Schools open in the detail panel; its header has "Open as page".
  const { open, isOpen } = useOpenRecord()
  const { clearPanel } = useDetailPanel()
  React.useEffect(() => () => clearPanel(), [clearPanel])
  const openSchool = (id: string, name: string) => open({ kind: "school", id }, name)

  const status: ListingStatus = isLoading
    ? "loading"
    : isError
      ? "error"
      : items.length === 0
        ? "empty"
        : "ready"

  return (
    <>
    <ListingView
      title="Schools"
      search={{ value: query, onChange: setQuery, placeholder: "Search schools, programmes…" }}
      filters={[
        {
          id: "run",
          label: "Run",
          value: runFilter,
          options: [
            { value: "all", label: "All runs" },
            ...(runs ?? []).map((run) => ({
              value: run.id,
              label: runTitle(run),
            })),
          ],
          onChange: setRunParam,
        },
        {
          id: "country",
          label: "Country",
          value: countryFilter,
          options: [
            { value: "all", label: "All countries" },
            ...countries.map((c) => ({ value: c, label: c })),
          ],
          onChange: setCountryParam,
        },
        {
          id: "tier",
          label: "Tier",
          value: tierFilter,
          options: [
            { value: "all", label: "All tiers" },
            ...SCHOOL_TIERS.map((t) => ({ value: t.value, label: t.label })),
            { value: "none", label: "No tier" },
          ],
          onChange: setTierParam,
        },
        {
          id: "tracked",
          label: "Applications",
          value: trackedFilter,
          options: [
            { value: "all", label: "All schools" },
            { value: "tracked", label: "Tracked in Applications" },
            { value: "untracked", label: "Not tracked yet" },
          ],
          onChange: setTrackedParam,
        },
      ]}
      viewStorageKey="schools:view"
      availableViews={["list", "grid"]}
      defaultView="grid"
      gridColumns={3}
      sort={{
        value: sort,
        options: [
          { value: "name", label: "Name A–Z" },
          { value: "programmes", label: "Most programmes" },
          { value: "faculty", label: "Most faculty" },
        ],
        onChange: setSortParam,
      }}
      items={sorted}
      renderItems={(view, { columns }) => {
        if (view === "grid") {
          return (
            <ul className={`grid gap-3 ${gridColumnsClass(columns)}`}>
              {sorted.map(({ school }) => (
                <li key={school.id} className="min-w-0">
                  <SchoolCard
                    school={school}
                    active={isOpen({ kind: "school", id: school.id })}
                    onOpen={() => openSchool(school.id, school.name)}
                  />
                </li>
              ))}
            </ul>
          )
        }
        return (
          <EntityList>
            {sorted.map(({ school }) => (
              <EntityRow
                key={school.id}
                onClick={() => openSchool(school.id, school.name)}
                active={isOpen({ kind: "school", id: school.id })}
                leading={<SchoolImage src={school.image_url} name={school.name} variant="thumb" />}
                title={school.name}
                subtitle={school.country || undefined}
                end={
                  <FactList
                    size="sm"
                    facts={[
                      { icon: BookOpen, value: String(school.programs.length), title: "Programmes" },
                      { icon: Users, value: String(schoolFacultyCount(school)), title: "Faculty" },
                    ]}
                  />
                }
                menu={<SchoolRowMenu school={school} className={ROW_MENU_POSITION} />}
              />
            ))}
          </EntityList>
        )
      }}
      status={status}
      errorText="Couldn't load schools across runs."
      onRetry={() => void refetch()}
      noMatchText="Nothing matches these filters."
      actions={addButton}
      empty={
        <EmptyState
          mascot="empty-box"
          title="No schools yet"
          description={
            canAdd
              ? "Schools appear as discovery saves programmes. Add one yourself if you already know where you want to look."
              : "Schools appear here once discovery saves programmes in a run. Start a run to begin research."
          }
          action={
            canAdd ? (
              addButton
            ) : (
              <Link to="/new" className={buttonVariants({ size: "sm" })}>New run</Link>
            )
          }
        />
      }
    />
    {adding > 0 && (
      <SchoolDialog
        key={adding}
        runOptions={runOptions}
        open
        onOpenChange={(o) => { if (!o) setAdding(0) }}
        onCreated={(school) => toastSuccess(`${school.name} added`)}
      />
    )}
    </>
  )
}

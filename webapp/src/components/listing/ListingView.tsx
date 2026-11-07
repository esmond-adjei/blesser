/* eslint-disable react/only-export-components -- column types and container helper ship with the listing shell */
import * as React from "react"
import { ArrowUpDown, Check, LayoutGrid, List, Rows3, SlidersHorizontal, SquareKanban } from "lucide-react"
import { HealthBanner } from "../layout/AppShell"
import { SearchInput } from "../filters/SearchInput"
import { Button } from "../ui/button"
import { Menu, MenuItem } from "../ui/menu"
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog"
import { ItemCardSkeleton } from "../cards/ItemCard"
import { EntityRowSkeleton } from "../entity/EntityRow"
import { EmptyState, ErrorState } from "../feedback/EmptyState"
import { cn } from "../../lib/utils"

export type ListingViewKind = "board" | "list" | "grid" | "cards"

export type GridColumnCount = 2 | 3 | 4

const GRID_COLUMN_CLASSES: Record<GridColumnCount, string> = {
  2: "grid-cols-1 @min-[30rem]:grid-cols-2",
  3: "grid-cols-1 @min-[30rem]:grid-cols-2 @min-[60rem]:grid-cols-3",
  4: "grid-cols-1 @min-[30rem]:grid-cols-2 @min-[60rem]:grid-cols-3 @min-[80rem]:grid-cols-4",
}

/** Container queries (not viewport) reflow when the detail rail resizes; explicit `grid-cols-1` stops a bare `grid` auto-sizing the column. */
export function gridColumnsClass(columns: GridColumnCount): string {
  return GRID_COLUMN_CLASSES[columns]
}

const VIEW_ORDER: ListingViewKind[] = ["board", "list", "grid", "cards"]

const VIEW_META: Record<ListingViewKind, { label: string; icon: React.ReactNode }> = {
  board: { label: "Board", icon: <SquareKanban className="size-4" /> },
  list: { label: "List", icon: <List className="size-4" /> },
  grid: { label: "Grid", icon: <LayoutGrid className="size-4" /> },
  cards: { label: "Cards", icon: <Rows3 className="size-4" /> },
}

export interface ListingFilterGroup {
  id: string
  label: string
  options: { value: string; label: string }[]
  value: string
  onChange: (value: string) => void
}

/** The page owns the value and applies the ordering. */
export interface ListingSort {
  options: { value: string; label: string }[]
  value: string
  onChange: (value: string) => void
}

export type ListingStatus = "loading" | "error" | "empty" | "ready"

function readStoredView(key: string, available: ListingViewKind[], fallback: ListingViewKind): ListingViewKind {
  try {
    const raw = window.localStorage.getItem(key)
    if (raw === "board" || raw === "list" || raw === "grid" || raw === "cards") {
      if (available.includes(raw)) return raw
    }
  } catch {
    // Private mode / SSR: fall through to the default.
  }
  return available.includes(fallback) ? fallback : available[0]
}

/** Pages own filtering, ordering and item rendering; the shell never wraps. */
export function ListingView<T>({
  title,
  search,
  filters = [],
  sort,
  actions,
  viewStorageKey,
  availableViews,
  defaultView,
  gridColumns = 3,
  items,
  renderItems,
  status,
  errorText = "Couldn't load items.",
  onRetry,
  empty,
  notice,
  noMatchText = "Nothing matches this search.",
}: {
  title: string
  search: { value: string; onChange: (value: string) => void; placeholder: string }
  filters?: ListingFilterGroup[]
  sort?: ListingSort
  /** Rendered last in the header row. */
  actions?: React.ReactNode
  viewStorageKey: string
  availableViews: [ListingViewKind, ...ListingViewKind[]]
  defaultView?: ListingViewKind
  gridColumns?: GridColumnCount
  /** Current items, used only for the no-match branch. */
  items: T[]
  /** Full items block for the active view, containers included. */
  renderItems: (view: ListingViewKind, grid: { columns: GridColumnCount }) => React.ReactNode
  status: ListingStatus
  errorText?: string
  onRetry?: () => void
  empty: React.ReactNode
  notice?: React.ReactNode
  noMatchText?: string
}) {
  const fallback = defaultView ?? availableViews[0]
  const [view, setView] = React.useState<ListingViewKind>(() =>
    readStoredView(viewStorageKey, availableViews, fallback),
  )
  const [filterOpen, setFilterOpen] = React.useState(false)

  // A stored view from before this listing narrowed its views falls back.
  const activeView = availableViews.includes(view) ? view : fallback

  const setStoredView = (next: ListingViewKind) => {
    setView(next)
    try {
      window.localStorage.setItem(viewStorageKey, next)
    } catch {
      // Non-fatal: the view just won't persist.
    }
  }

  // A group counts as active when it moved off its first (default) option.
  const activeFilterCount = filters.filter(
    (g) => g.options.length > 0 && g.value !== g.options[0].value,
  ).length

  const activeSortLabel =
    sort?.options.find((o) => o.value === sort.value)?.label
    ?? sort?.options[0]?.label
    ?? "Sort"

  return (
    <div className="@container space-y-4">
      <HealthBanner />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="type-page-title">{title}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <SearchInput
            value={search.value}
            onChange={search.onChange}
            placeholder={search.placeholder}
          />
          {availableViews.length > 1 && (
            <div
              className="g-seg"
              role="group"
              aria-label="View type"
            >
              {VIEW_ORDER.filter((kind) => availableViews.includes(kind)).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  data-tooltip={VIEW_META[kind].label}
                  aria-label={VIEW_META[kind].label}
                  aria-pressed={activeView === kind}
                  onClick={() => setStoredView(kind)}
                  className="cursor-pointer"
                >
                  {VIEW_META[kind].icon}
                </button>
              ))}
            </div>
          )}
          {sort && sort.options.length > 0 && (
            <Menu
              label="Sort by"
              trigger={
                <Button type="button" variant="outline" size="sm" aria-label={`Sort by: ${activeSortLabel}`}>
                  <ArrowUpDown />
                  <span className="max-w-28 truncate">{activeSortLabel}</span>
                </Button>
              }
            >
              {sort.options.map((opt) => (
                <MenuItem key={opt.value} onSelect={() => sort.onChange(opt.value)}>
                  <span className="min-w-0 flex-1">{opt.label}</span>
                  {opt.value === sort.value && <Check className="size-4 shrink-0 text-primary" />}
                </MenuItem>
              ))}
            </Menu>
          )}
          {filters.length > 0 && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setFilterOpen(true)}
                aria-label="Filters"
                data-tooltip="Narrow this list with filters"
                className="relative"
              >
                <SlidersHorizontal />
                Filters
                {activeFilterCount > 0 && (
                  <span
                    aria-label={`${activeFilterCount} active filters`}
                    className="absolute -right-1.5 -top-1.5 inline-flex size-4 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
                  >
                    {activeFilterCount}
                  </span>
                )}
              </Button>
              <Dialog open={filterOpen} onOpenChange={setFilterOpen}>
                <DialogContent onClose={() => setFilterOpen(false)} className="max-w-lg">
                  <DialogHeader>
                    <DialogTitle>Filters</DialogTitle>
                  </DialogHeader>
                  <DialogBody className="space-y-4">
                    {filters.map((group) => (
                      <section key={group.id}>
                        <h3 className="mb-1.5 px-1 type-group-label">
                          {group.label}
                        </h3>
                        <div
                          className="space-y-0.5"
                          role="radiogroup"
                          aria-label={group.label}
                        >
                          {group.options.map((opt) => {
                            const active = opt.value === group.value
                            return (
                              <button
                                key={opt.value}
                                type="button"
                                role="radio"
                                aria-checked={active}
                                onClick={() => group.onChange(opt.value)}
                                className={cn(
                                  "flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                                  active
                                    ? "bg-accent font-medium text-accent-foreground"
                                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                                )}
                              >
                                <span className="min-w-0 flex-1 wrap-break-word">{opt.label}</span>
                                {active && <Check className="size-4 shrink-0 text-primary" />}
                              </button>
                            )
                          })}
                        </div>
                      </section>
                    ))}
                  </DialogBody>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setFilterOpen(false)}>Done</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </>
          )}
          {actions}
        </div>
      </div>

      {status === "loading" ? (
        // Same anatomy as the loaded items, so nothing jumps on arrival.
        activeView === "list" ? (
          <div className="divide-y divide-border/50" aria-busy="true" aria-label="Loading">
            {Array.from({ length: 6 }, (_, i) => <EntityRowSkeleton key={i} />)}
          </div>
        ) : (
          <ul className={`grid gap-3 ${gridColumnsClass(gridColumns)}`} aria-busy="true" aria-label="Loading">
            {Array.from({ length: gridColumns * 2 }, (_, i) => <li key={i}><ItemCardSkeleton /></li>)}
          </ul>
        )
      ) : status === "error" ? (
        <ErrorState title="Couldn't load this list" description={errorText} onRetry={onRetry} />
      ) : status === "empty" ? (
        empty
      ) : (
        <>
          {notice}
          {items.length === 0 ? (
            <EmptyState compact mascot="search-empty" title="No matches" description={noMatchText} />
          ) : (
            renderItems(activeView, { columns: gridColumns })
          )}
        </>
      )}
    </div>
  )
}

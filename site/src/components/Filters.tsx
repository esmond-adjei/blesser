import { Field, Select, buttonVariants } from "@blesser/ui"
import type { Facets } from "../lib/api"
import { CATEGORY_LABELS, CLOSING_WITHIN, KIND_LABELS } from "../lib/format"
import type { Filters as FilterState } from "../lib/listing"
import { SearchIcon } from "./icons"

const count = (facets: Facets | null, group: "categories" | "kinds", key: string) => {
  const n = facets?.[group].find((f) => f.key === key)?.count
  return n ? ` (${n})` : ""
}

/** A plain GET form, so filtering works with JavaScript off. */
export function Filters({ filters, facets }: { filters: FilterState; facets: Facets | null }) {
  const kinds = Object.keys(KIND_LABELS).filter(
    (k) => k === filters.kind || !facets || facets.kinds.some((f) => f.key === k && f.count > 0),
  )
  return (
    <form method="get" action="/opportunities" role="search" className="rounded-lg border border-separator bg-surface p-5 shadow-elevation-1">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-[1.5fr_repeat(4,minmax(0,1fr))]">
        <Field label="Search" id="f-q" name="q" type="search" defaultValue={filters.q} placeholder="Title, organisation or topic" />
        <Field label="For" id="f-category">
          <Select name="category" defaultValue={filters.category}>
            <option value="">Everyone</option>
            {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {`${label}${count(facets, "categories", key)}`}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Kind" id="f-kind">
          <Select name="kind" defaultValue={filters.kind}>
            <option value="">All kinds</option>
            {kinds.map((key) => (
              <option key={key} value={key}>
                {`${KIND_LABELS[key]}${count(facets, "kinds", key)}`}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Closing within" id="f-closing">
          <Select name="closing_within" defaultValue={filters.closing_within}>
            <option value="">Any time</option>
            {CLOSING_WITHIN.map((d) => (
              <option key={d} value={String(d)}>
                {`${d} days`}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Sort" id="f-sort">
          <Select name="sort" defaultValue={filters.sort}>
            <option value="deadline">Closing soonest</option>
            <option value="new">Newest</option>
          </Select>
        </Field>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="submit" className={buttonVariants({ variant: "brand" })}>
          <SearchIcon />
          Show opportunities
        </button>
        <a href="/opportunities" className={buttonVariants({ variant: "quiet" })}>
          Clear filters
        </a>
      </div>
    </form>
  )
}


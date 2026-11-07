# PageHeader

The page header names a list page and holds the controls that act on everything below it.

In the app: the header of `components/listing/ListingView.tsx`, used by Matches, Schools, Applications and Outbox. Above it, the app shell's 48px top bar carries breadcrumbs, notifications and the panel toggles (see docs/02-app.md).

Markup: a wrapping row, bottom-aligned, 12px gap: the title (`title-2`, `.type-page-title`) left; on the right, in this order: a SearchField, a SegmentedControl of icon-only views (Board, List, Grid, Cards; each with a tooltip), Sort (`outline` `sm` with the current order, opening a Menu), and Filters (`outline` `sm`, opening a dialog, with a 16px `tint` count badge on its corner when filters are on).

The page's view choice is remembered per browser. Grids use 12px gaps.

Don't: put the page's primary creation action here when the sidebar already has it (New run).

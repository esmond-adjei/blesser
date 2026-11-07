# SegmentedControl

A segmented control switches between two to five views of the same thing: tabs on the run page and in settings, the list/grid/board toggle, range pickers.

In the app: `TabsList` and `TabsTrigger` in `components/ui/tabs.tsx` (role `tablist`, `tab`, `aria-selected`) and the view toggle in `ListingView` (`aria-pressed`, icon-only with `aria-label` and a tooltip). Both render `.g-seg`.

The selected segment is a raised `surface-raised` thumb with `elevation-1` on a `fill-quiet` track; height `control-md`. Run-page tabs stretch to the width, scroll sideways when narrow, carry a count in brackets ("Faculty agents (12)") and a small `tint` badge for active tasks.

Do: keep segments equal in importance. Don't: use it for navigation between pages, or for more than five options (use a menu).

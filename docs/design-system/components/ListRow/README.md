# ListRow

Rows in a bordered group are the app's list view: Matches, Schools, Outbox, Applications and a run's candidates.

In the app: `EntityList` and `EntityRow` in `components/entity/EntityRow.tsx`. The list is `.g-list`: `surface`, `radius-lg`, a 1px `separator` border (`control-border`, which now equals it), full-width hairlines between rows. `EntityList bare` drops the box and keeps the hairlines for lists inside a panel.

Markup: `.g-list` holding `.g-row`s. A row is a leading avatar, thumbnail or icon tile, a `.g-row__main` with `.g-row__title` (14px, 600, one line) and `.g-row__sub` (`caption`, `label-secondary`, one line), and a `.g-row__trail` for at most two items (a pill and a date, or the FitScore).

Look: at least 56px tall (40px compact), 12px side padding, 12px gap. Hover fills `fill-quiet` at 50%; the row whose detail panel is open fills `tint-soft`. Focus is an inset 2px ring. Rows can indent one or two levels and carry a leading checkbox while the list is selecting (visible at 40% until hovered or checked).

Each row can float a RowMenu (see SidebarRow) vertically centred at its end; it shows on hover or focus, over the trailing items.

Examples: a match is avatar, name, programme and school, Best fit, FitScore. A draft is avatar, professor, subject, its status pill when it is news, and the date.

Don't: show more than two trailing items; move the rest to the detail panel.

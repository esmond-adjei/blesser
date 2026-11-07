# MatchCard

A match card shows a professor matched to the applicant in grid view: who they are, where, why they fit and how well.

In the app: `ProfessorCard` in `components/dossier/ProfessorCard.tsx`, built on `CoverCard` (Matches and a run's candidates, grid view). In list view the same match is a ListRow.

Anatomy, on `.g-ecard`: a 44px avatar beside the name (`.g-ecard__title`, up to two lines) and programme and school (`.g-ecard__meta`, one line); the rationale (14px `label`, two lines); then the signal row: `.g-best` on the single best match, the status pill when it is news, and the FitScore pushed to the end.

States: the whole card is one button (an invisible cover over it, so inner parts stay unclickable); hover lifts 1px with `elevation-1`; the match open in the detail panel, or picked while selecting for a PDF export, gets a 2px `tint` border; while selecting a circle check sits top-left. A RowMenu (`g-rowmenu--card`) shows top-right on hover.

Rules: exactly one card per list gets Best fit. Weak matches stay at full opacity; the fit band says they are weak.

The bundle's other formats (`.g-ecard--feature`, `.g-mention`, `.g-peek`, `.g-paper`, `.g-stats`) have no consumer today.

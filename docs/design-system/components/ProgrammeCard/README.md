# ProgrammeCard

A programme card is one degree programme on a school or run page: its name, how many faculty and candidates are known there, and a link to the department.

In the app: `ProgrammeCard` in `components/cards/EntityCards.tsx`, inside a `CardGrid` (two columns once the container is wide enough, one in a narrow panel, 12px gaps). The same file draws `PersonCard` (avatar, name, place, status, FitScore or "Not scored yet") and `LinkedApplicationCard` (school thumbnail, programme, school, status pill, deadline) on the same anatomy.

Anatomy, on `.g-ecard` (the app's `ItemCard`): the name (up to two lines), then a fact list in `caption` `label-secondary` with 14px icons: faculty (users) and, when there are any, candidates (target). The department link is a 28px icon button in the top-right corner (`label-tertiary`, `tint` on hover), outside the card's open button so it stays its own link.

States: the whole card opens the programme; the one open in the detail panel gets a 2px `tint` border.

Rules: programmes have no status pill and no fit of their own.

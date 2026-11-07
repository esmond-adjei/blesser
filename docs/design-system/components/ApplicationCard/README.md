# ApplicationCard

An application card tracks one programme the applicant is applying to: what, where, when it is due, how much is done, and who they hope to work with.

The consumer supplies an `Application` (school, program, degree type, location, `deadline`, `status`, `requirements` with `done`, `professors`, `feeWaiver`, `offer`, `schoolImageUrl`).

| Format | Markup | Use in |
|---|---|---|
| Board | `.g-ecard.g-ecard--board` inside a status column | Applications, board view (the default): Wishlist, Applying, Submitted, Interview, Offer, Rejected. |
| Tile | `.g-ecard` with `.g-ecard__media` | Applications, grid view, and the "Your applications" strip on a school page. |
| Row | ListRow with a `.g-date` leading | Upcoming deadlines lists, sorted by date. |

Anatomy (board): the deadline as a `.g-date` calendar leaf, programme (title, one line), school and city (meta), requirements as `.g-segments` with "4 of 6", then facts as `.g-tag` (degree, Fee waiver) and the linked professors as a `.g-avatars` stack at the end.

Rules:
- The deadline leaf's month turns `caution` (`data-soon`) inside seven days, and a "5 days left" caution pill replaces the degree tag. Past deadlines show "Closed" in a neutral pill; never red text.
- The column header carries the status pill; board cards do not repeat it. Tiles and rows, which mix statuses, show it in the signal row.
- Funding (`offer`) appears as one meta line once known, most useful on Submitted, Interview and Offer cards.
- Without a school image, `.g-ecard__media` holds `.g-crest` (brand field, initials, lens rings); with one, an `<img>` with `object-fit: cover`, or `contain` on white for a near-square crest.

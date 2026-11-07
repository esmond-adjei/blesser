# Pitch deck guide

A 12-slide seed narrative built from the five Slide templates. One idea per slide, 25 words of body at most, one gold mark per slide.

| # | Template | Ground | Content |
|---|---|---|---|
| 1 | Cover | brand | Logo, kicker "Seed round 2026", hero "Find the professor, not just the *programme*." |
| 2 | Statement | canvas | The problem in one sentence: "Applicants email forty professors. Most never reply, because most emails could be to anyone." |
| 3 | Metric | surface | The size of the pain: one number with its source in `footnote`. |
| 4 | Split | surface | Who it is for: the applicant, the timeline, the stakes. |
| 5 | Statement | brand | The insight: "Fit is in the papers. Nobody has time to read them all." |
| 6 | Product | canvas | Dossier: every professor ranked by what they publish. |
| 7 | Product | canvas | Outbox: a personal draft, approved by the applicant. |
| 8 | Split | surface | How it works: the four Steps, and why it is grounded (OpenAlex, deterministic tools). |
| 9 | Metric | surface | Traction: one number. |
| 10 | Split | canvas | Business model: the two plans from PriceCard, as a table. |
| 11 | Split | surface | Team. Names and one line each; photos in circles at 160px if used. |
| 12 | Cover | brand | Close: the ask in `display`, contact line, Gradis sticker bottom-right. |

Grid: 1920×1080, 96px side margins, `space-16` top, 144px bottom reserved for the footer line (wordmark left, page number right, 22px `label-tertiary`). Titles align to the top-left margin; metric and statement slides centre vertically.

Type on slides: hero 168px serif, statement 88px serif, title 96px sans, body 36px sans, metric 280px sans with the unit at half size in `label-tertiary`.

Charts: `tint` for the company's series, `label-tertiary` for comparisons, `gold` only for the single point being made; no gridlines beyond a `separator` baseline; label values directly instead of legends.

Section breaks and the close use the `brand` ground; never more than three brand slides in a deck. Product slides show the real interface at 2× scale, cropped by the bottom edge, in a `radius-2xl`-equivalent 40px frame with `elevation-3`.

For Keynote or Google Slides: install Instrument Sans and Newsreader, set the theme colours to `brand`, `tint`, `gold`, `label`, `label-secondary`, `canvas`, and build one master per template.

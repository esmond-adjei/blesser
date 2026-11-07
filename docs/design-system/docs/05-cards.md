# Entity cards

Every record in Graduator (a match, a school, a programme, an application, a draft, a run, a document) is drawn from one anatomy in a few formats, so the same thing looks the same wherever it appears.

## Anatomy

Top to bottom, each part optional except the title:

1. **Media**: `.g-ecard__media`, inset 6px so its 8px corners sit inside the 14px card. A photo (`object-fit: cover`), a crest on white (`contain`), or the `.g-crest` fallback (brand navy, initials, lens rings).
2. **Kind line**: `.g-ecard__kind`, the kind's icon and word, where the grid mixes kinds.
3. **Title**: `.g-ecard__title`, the record's name, one or two lines.
4. **Meta**: `.g-ecard__meta`, where it belongs (programme and school, country), one line.
5. **Body**: one or two sentences of substance (a match's rationale), clamped to two lines; or a fact list (icon and value in `caption`).
6. **Signal row**: `.g-ecard__signal`, pinned to the bottom: markers and status first (Best fit, a status pill, `.g-tag` facts), then the measure (FitScore, `.g-segments`) or people (`.g-avatars`) at the end.

## Formats

| Format | Markup | Where |
|---|---|---|
| Row | ListRow (`EntityRow` in a `.g-list`) | List views: Matches, Schools, Outbox, Applications, a run's candidates |
| Tile | `.g-ecard` (`ItemCard`, or `CoverCard` in `components/cards/CoverCard.tsx`: a full-bleed open button under the content) | Grid views and detail pages |
| Board | `.g-ecard--board` | Application status columns |
| Sidebar row | SidebarRow | Runs and chats |
| Record card | RecordChip | Records in Gradis answers and run traces |

`.g-ecard--feature`, `.g-mention` and `.g-peek` remain in the bundle without a consumer.

## Which entity, which format

| Entity | Row | Tile | Board | Elsewhere |
|---|---|---|---|---|
| Match (professor) | Matches, run | Matches grid (MatchCard), detail pages (`PersonCard`) | | Record card in Gradis |
| School | Schools | Schools grid (SchoolCard) | | |
| Programme | | School and run pages (ProgrammeCard) | | |
| Application | Applications list | Applications grid, detail pages | Applications board (ApplicationCard) | |
| Draft | Outbox | | | Opens on its own page |
| Run | | | | SidebarRow; the run page |
| Document | | Documents grid (DocumentCard) | | |

## Shared rules

- Tiles rest on `surface` with a 1px `separator` border and no shadow, `radius-lg`, 16px padding. Hover lifts 1px with `elevation-1`; the record open in the detail panel, or picked while selecting, gets a 2px `tint` border.
- The whole card is one button or link: an invisible cover fills the card and the visible parts ignore the pointer. Inner links (a department page) and the RowMenu sit above the cover as siblings, so they never open the card.
- One measure per card. Fit is the measure for people, requirements for applications.
- Gold appears once per list: the single Best fit marker. Saved-record chips are the other gold.
- Grids use 12px gaps; cards in a row share a height, with the signal row pinned to the bottom. Never cards inside cards.
- In dark mode cards are `surface` on `canvas`; columns never add their own lighter ground behind cards.

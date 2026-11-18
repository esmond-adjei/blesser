Opportunities, made visible. Blesser helps startups, researchers and students in Ghana find grants, fellowships, scholarships and accelerators, and see them through to a yes. The system should feel like good news arriving: bright, warm and steady. It serves three surfaces: the public site, the member app and the admin console.

## Personality

- **Hopeful, not hype.** Every screen points at what someone can still do. Deadlines are time left, not alarms. Rejections are "Not this time".
- **Sunlit, not loud.** One warm hue (`sun`) does the work; `forest` grounds it; `bloom` is saved for celebration.
- **Plain and local.** Short sentences, real amounts in the stated currency, Ghanaian date order.

## Content fundamentals

- Address the reader as "you"; the product speaks as "we" only in emails and legal pages.
- Sentence case everywhere: buttons, titles, chips. "Track this opportunity", not "Track This Opportunity".
- Buttons start with a verb and say what happens: "Track", "Add to calendar", "Publish", "Start a scan". The toast confirms in the past tense: "Tracked", "Published".
- Deadlines: "12 days to go", "2 days left", "Closes today", "Rolling, apply any time". Dates read day month year: "21 Nov 2026". Times in Africa/Accra.
- Money as the source states it: "Up to GHS 120,000", "USD 50,000 equity-free". Never convert or round.
- Outcomes: "Accepted" with "Congratulations"; a rejection is "Not this time" with "Keep going, more are coming". Never "Rejected" or "Failed".
- Errors say what happened and what to do: "That link didn't open. Check the address and try again." No apologies, no exclamation marks.
- Trust notes are specific: "Checked 2 days ago from the official page". Always tell people to confirm on the official page before applying.
- No emoji in product UI or emails.
- No middle dot separators and no em dashes. Separate metadata with space or commas; a plain dash only in date ranges ("16 - 22 Nov 2026").
- Say each thing once. A component never shows the same fact twice (a status as both a stepper and a label) or offers the same action twice; secondary actions live in one menu.

## Colour

- Ground every page with `canvas` (plain white in light mode); put content on `surface` cards, which separate from it by `elevation-1` and `separator`, not by colour. Use `surface-sunk` for wells and quiet fills inside a card.
- Text: `ink` for primary, `ink-secondary` for supporting copy, `ink-tertiary` for metadata. All three pass 4.5:1 on canvas, surface and surface-sunk in both themes.
- `sun` is the primary action and the brand's warmth: the primary button, the logo's sun, the empty-state sunrise, the current step, the active nav marker. Text on it is always `on-sun`, never white. One sun button per view.
- `forest` grounds the brand: the logo's steps and wordmark, the icon tile, the public site's footer band and feature bands, the selected nav item, filled secondary actions (`brand` button). Text on it is `on-forest`.
- `bloom` is for celebration only: an accepted application, a first tracked opportunity. Never use it for warnings or decoration elsewhere.
- Soft washes (`sun-soft`, `forest-soft`, `bloom-soft`, `info-soft`, `caution-soft`, `critical-soft`) sit behind their own ink token (`sun-ink`, `link`, `bloom-ink`, `info`, `caution`, `critical`).
- `critical` is for errors and destructive actions only. A near deadline is `sun` or `bloom`, never red.
- Status always carries a word or icon as well as colour.
- Dark mode sits on a neutral near-black (`canvas` #191919) with surfaces a step lighter: the same roles, with lighter inks and a deeper `forest`. The logo's steps and wordmark turn white there.

## Typography

- Display face: Bricolage Grotesque (Google Fonts, variable 500 to 800). It carries the personality, so use it with restraint: `hero` on the public site, `title-1` and `title-2` for page titles, `numeral` for the countdown and single figures, and empty-state titles.
- Text face: Figtree (Google Fonts, 400 to 800) for everything else. `body` is 16px/24px; card titles use `title-3` at 700.
- Wordmark: "blesser" in lowercase Figtree 800, `-0.04em`, `forest`, set beside the logo with a `space-1` gap. It is the only lowercase use of the name; in running text it stays "Blesser".
- Mono: JetBrains Mono for `code` in the admin audit log and agent traces only.
- 12px (`caption`) is the floor. 600 and 700 are the only bold weights.
- Headings use `text-wrap: balance`; running text stays under `reading-max` (680px).
- Use tabular figures (`font-variant-numeric: tabular-nums`) for counts, amounts in tables and countdowns.

## Shape, space and depth

- Every pressable thing is a pill (`radius-full`): buttons, chips, the countdown, filter toggles.
- Cards and dialogs use `radius-lg` (20px); inputs `radius-sm`; public site bands `radius-xl`.
- Spacing runs on a 4px base. Card padding is `space-5`, grid gaps `space-6`, member-app sections `space-8`, public-site sections `space-12`.
- Depth is soft daylight: `elevation-1` for resting cards, `elevation-2` for hover and menus, `elevation-3` for dialogs. Dark mode trades shadows for a 1px light edge.
- Content max width is `content-max` (1120px); keep a `space-4` gutter on phones.

## Motion

- Quick and calm, all from `motion.css`: 120ms to leave, 180ms for small things, 260ms for dialogs and sheets, ease-out in and ease-in out.
- Dialogs rise 10px and scale from 98%; menus, popovers and tooltips grow from their trigger; the mobile nav sheet slides from its edge. Everything that opens also animates closed.
- Content that mounts (a page, a view switch, a tab panel, list rows) rises 6px and fades in, siblings staggered 24ms and capped at eight.
- Segmented controls and view switchers slide one pill to the selected option. Cards lift 2px on hover.
- One celebration: when an application moves to Accepted, the track fills `bloom` left to right over 600ms.
- Respect `prefers-reduced-motion`: fades only, no movement, no lifts.

## Focus and accessibility

- Focus ring: 2px solid `focus` with a 2px offset on every interactive element. It is 5:1 or better on every surface in both themes.
- `control-border` meets 3:1 on canvas, surface and surface-sunk, for checkboxes and secondary buttons.
- Text fields are soft on purpose: `input-border` at rest, `input-border-hover` on hover, and on focus the border turns `focus` with a 3px `focus-soft` halo instead of the offset ring.
- Hover, pressed and highlighted rows and menu items use `highlight`, which is lighter than every surface in dark mode so it always shows.
- Touch targets are at least 40px (`control-md`); use `control-lg` for primary actions on phones.

## Iconography

- Lucide icons (the `lucide-react` package), 24-unit grid, 1.75px stroke, drawn at 18px in buttons, 14px in chips and 20px in navigation. Icons inherit `currentColor`.
- Icons accompany a word; icon-only buttons need an `aria-label` and a tooltip.
- The Sunrise mark (see Logos), a half sun rising behind three steps, is the only custom glyph. Its geometry is the brand's one motif: the empty-state sunrise is its sun alone on the horizon, and the cover is built from it. Do not draw other illustrations, and do not use people illustrations in empty states.

## The three surfaces

- **Public site**: editorial and generous. `hero` headline, forest bands, opportunity cards in a three-column grid, one sun button per section. Signed-out visitors can browse everything published and are invited to create an account to track.
- **Member app**: calm and dense. `title-2` page titles, cards and lists on `canvas`, sidebar with the forest selected state, countdowns everywhere a deadline appears.
- **Admin console**: the same tokens at higher density. Tables over cards, `callout` cell text, `code` for ids and traces, `critical` for hide and delete. Publication state uses chips: Draft (neutral), In review (`sun`), Published (`forest`), Hidden (`critical`).

## Menus

- Rows and cards carry one action menu: right-click, long-press on touch, or the "More" button all open the same list. The row shows only its primary action (Track, or the status) beside it.
- Menu items: icon, verb-first label, a separator before outward links and before Remove, which is `critical`. "Move to" opens a submenu of statuses.

## Layouts

Screen patterns live in the Layouts group, built only from these tokens, the components and the `ly-*` classes in the bundle stylesheet:

- **App shell**: sidebar, top bar with search and the List / Gallery / Board / Calendar view switcher.
- **List view** and **Gallery view**: the same opportunities as dense rows or as cards.
- **Application board**: applications as a kanban from Saved to Decision.
- **Deadline calendar**: deadlines, interviews and to-dos by day, with the week's agenda.
- **Scan**: what to look for, the running scan's tasks, and finds labelled by source (the Blesser catalog or the web).
- **Assistant**: chat with visible tool steps and opportunities as trackable rows.
- **To-dos**: the steps that move an application forward, grouped by when they are due.
- **Opportunity detail** and the **Extension side panel**.

Every layout sits on `canvas`, puts content on `surface`, keeps one sun action per region and shows deadlines as countdowns.


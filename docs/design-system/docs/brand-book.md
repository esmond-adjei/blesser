Graduator helps PhD and master's applicants find the professors they actually want to work with: agents read each professor's papers, rank them by fit and draft the first email, and the applicant decides what gets sent. The design has one job: make a stressful, high-stakes search feel calm, precise and in the applicant's control.

This system serves three surfaces with one vocabulary: the web app, the landing page and the pitch deck. The web app is the reference: where it and this book differ, the app wins and the book is corrected. The app, landing and deck guides apply it to each surface; `01-decisions.md` explains what changed from the first shipped UI and why.

## Principles

1. **Content is the interface.** Professors, papers, drafts and deadlines are the product. Chrome recedes: no borders where spacing will do, no colour where weight will do, no shadow where a surface change will do.
2. **One tint, one needle.** `tint` blue is the only colour that means "you can act". `gold` is the compass needle from the logo and appears once per view, on the single most important thing (the best match, the key number). Everything else is navy-ink on neutral.
3. **Evidence over assertion.** Every score shows its number; every claim links to the paper or page it came from. Fit is a measure in one hue, never a verdict in traffic-light colours.
4. **The applicant decides.** Nothing is sent, deleted or spent without a clear, named action. Primary buttons say exactly what happens ("Approve draft"), and destructive confirmations say what will be lost, in numbers.
5. **Depth means "floating".** Resting content is told apart by a surface change and a `separator` hairline. Menus, popovers, toasts, dialogs and the floating chat cast shadows.

## Voice and content

- Plain, calm, specific. Short sentences. Say what happened and what happens next: "Draft approved. Copy it from the Outbox to send."
- Sentence case everywhere: buttons, titles, menu items, pills. No uppercase eyebrows or labels; the one exception is the sidebar's section labels (Workspace, Runs, Chats), set in capitals as small `label-tertiary` headings.
- Second person for the applicant ("your interests"), third person for agents ("Gradis read 46 papers"). Gradis speaks in first person only in chat.
- Name things by the product's nouns: run, dossier, candidate, professor, programme, draft, Outbox, application. Never "lead", "prospect" or "contact" in the UI.
- British spelling, as the product already writes it: programme, colour, personalised.
- Numbers as numerals, percentages whole ("91%"), dates as "Dec 1" in the app and "1 December 2026" in legal and deck copy.
- No em dashes and no middle dots. Where a sentence wants a dash, write two sentences, or use a colon or commas; keep an em dash only when nothing else carries the break. Separate facts in the interface with a comma ("Carnegie Mellon University, Robotics Institute PhD"), a line break, or their own element (a `.g-tag`, a second meta line), never with `·`, `•`, `|` or `/`. Run names read "Robotics, United States"; paper lines read "CoRL 2025".
- No emoji, no exclamation marks, no "Oops". Errors say what failed and how to fix it: "Your model key was rejected. Check it in Settings → Models."
- Real copy to model on: "Nothing is ever sent for you." "Find the professors you actually want to work with." "Scores come from embeddings, not from an LLM's guess."

## Colour

The palette is neutral-first with two brand hues. Every text token's note names the grounds it reads on; each pair meets WCAG 4.5:1 in both themes.

- **Grounds:** `canvas` → `surface` → `surface-raised` (floating). In the app's light theme the reading area is `surface` (white) and the panes beside it (sidebar, detail panel) sit on `canvas`; in dark the reading area is `canvas` and the detail panel lifts to `surface`. `fill-quiet` and `fill` are for hover, selected rows, wells, chips and the user's chat bubble. Dark mode is neutral grey (`#191919`, `#202020`, near-white text); the brand comes through `tint`, `gold` and the logo, not the grounds.
- **Text:** `label` (navy-black ink in light, the existing near-white in dark), `label-secondary`, `label-tertiary`. Never use opacity to dim text; use the next label token.
- **Action:** `tint` for primary buttons, links, switches and selection; `on-tint` on it; `tint-soft` for secondary buttons and selected rows; `focus` for keyboard focus.
- **Brand:** `brand` navy for large identity fields (deck covers, the landing page's closing band, the app icon tile) with `on-brand` text; `gold` for the needle; `gold-ink` when gold must be text on a light ground; `gold-soft` for saved-record chips; `mist` for light panels on navy in the deck.
- **Status:** `positive`, `caution`, `critical` with their `*-soft` grounds, always with a word. `tint` doubles as info.
- **Fit:** `fit-strong`, `fit-moderate`, `fit-weak`.
- **Record kinds:** Gradis's record cards give each kind a light tone (teal professor, rose candidate, blue programme, indigo school, emerald application, sky draft, violet run, gold CV proposal) as a second cue beside the kind's word and icon. Nowhere else carries per-kind colour. See RecordChip.
- **Materials:** `material` for translucent bars; black at 50% behind dialogs; `scrim` behind phone sheets and the docked chat on narrow screens.

Do: let 90% of any screen be canvas, surface and label. Don't: add colour per kind outside record cards, gradients, or tints of the brand navy as backgrounds in the app.

## Typography

Two families with fixed roles, plus a code mono:

- **Instrument Sans** (`sans`, Google Fonts, variable 400–700) for everything you use: interface, headlines, numbers. Tight negative tracking at display sizes, near zero at text sizes.
- **Newsreader** (`serif`, Google Fonts, optical sizes) for everything you read as a statement: the landing hero, deck covers and statement slides, quotations. Never in the app.
- **ui-monospace** (`mono`) only for keys, ids and code.

Styles, by role (sizes in px, line-height in brackets):

| Role | Style | Size | Where |
|---|---|---|---|
| Editorial | `hero` | 88 (92) serif 500 | Landing hero, deck cover |
| | `statement` | 48 (56) serif | Statement band and slides |
| | `quote` | 24 (34) serif italic | Testimonials, quoted paper titles |
| Display | `display` | 64 (68) | Landing section headlines, slide titles |
| | `title-1` | 40 (46) | Pricing, FAQ, deck metrics |
| | `lead` | 21 (30) | The paragraph under a headline |
| | `eyebrow` | 17 (22) 600, gold-ink | Above hero and section headlines |
| Interface | `title-2` | 28 (34) | App page titles |
| | `title-3` | 20 (26) | Dialog and panel titles |
| | `headline` | 15 (20) 600 | Row and card titles |
| | `body` | 15 (22) | Default interface text |
| | `reading` | 17 (28) | Drafts, chat answers, legal, landing body |
| | `callout` | 14 (20) | Row subtitles, hints, button labels |
| | `footnote` | 13 (18) | Timestamps, counts, dense tables |
| | `caption` | 12 (16) 500 | Pills, badges, tooltips |
| | `numeral` | 15 (20) 600 tabular | Scores, counts, money |

In the app, components name the role, not the size: `.type-page-title` (`title-2`), `.type-panel-title` (`title-3`), `.type-section-title` and `.type-group-label` (13px 600, `label-secondary`), `.type-meta` (`callout`, `label-secondary`) and `.type-caption` (`caption`, `label-secondary`). Tailwind's steps are re-pointed at the scale: `text-xs` 12, `text-compact` 13, `text-sm` 14, `text-base` 15, `text-lg` 17, `text-xl` 20, `text-2xl` 24, `text-3xl` 28. Body text is 15/22; compact surfaces (the sidebar, cards, the chat dock, menus) set `text-sm` (14) once at their root. Paragraphs use a 1.6 line height.

Rules: 12px is the floor (the `.g-kbd` hint, at 10px, is the one exception). One `title-2` per page. Weight 600 is the only bold (Tailwind's `font-bold` maps to it). Reading columns stop around 680px (the app uses `max-w-2xl`, 672px). Numbers use tabular figures of the sans; mono is for keys, ids and tool parameters.

## Layout and spacing

- A 4px grid: `space-1` to `space-12` inside the app, `space-16` to `space-32` for landing and deck rhythm.
- App: a resizable sidebar (`sidebar-width` by default) on `canvas`; a 48px top bar; list pages up to `content-max` (1080px) with 16px gutters (24px from 640px) and 24px of top padding; grids use 12px gaps.
- Landing: content within `site-max`; sections separated by space (`space-32`), not rules or alternating backgrounds, except one `brand` band near the end.
- Controls share heights: `control-sm` 28 (small buttons, icon buttons, control pills), `control-md` 36 (buttons, inputs, segmented controls, chat rows), `control-lg` 44, `control-xl` 52 (marketing).

## Shape

Radii are concentric: an inner element's radius is the outer radius minus the inset between them.

- `radius-xs` 4 (checkbox, kbd), `radius-sm` 6 (pills, row-menu triggers), `radius-md` 10 (controls, menu items, sidebar rows), `radius-lg` 14 (lists, entity cards, menus, the composer), `radius-xl` 20 (dialogs, popovers, settings panels, chat bubbles), `radius-2xl` 28 (phone sheets, landing and deck panels), `radius-full` (New run, marketing CTAs, chips, control pills, send buttons, avatars, switches).
- Capsules mark "start something" (New run, landing CTAs, send) and small removable or pickable things (chips, control pills). Everything else in the app is a rounded rectangle.

## Depth and materials

- Resting surfaces (grouped lists, entity cards, settings panels, the composer) have a 1px `separator` border and no shadow. `elevation-1` is for a hovered card, empty-state panels and skeleton cards (a hairline in dark). `elevation-2` for menus, popovers, tooltips and toasts (menus and popovers also keep the hairline border). `elevation-3` for dialogs, the floating chat and the landing product frame.
- Translucency only where content scrolls under chrome: the app's top bar and the landing header use `material` with `blur-thin`. Dialogs sit on plain black at 50%, no blur.
- No gradients, glows or coloured shadows.

## Motion

Motion explains where something came from; it never decorates.

- Hover and colour changes take 150ms in the app (Tailwind's default; the bundle uses `duration-instant`, 100ms). `duration-quick` (200ms) for tooltips, scrims, the sidebar and panels opening; `duration-standard` (320ms) for dialogs; `duration-slow` (600ms) for progress and score bars and landing reveals.
- Easing: `cubic-bezier(0.2, 0.7, 0.3, 1)` (Tailwind's `ease-out` in the app) for things arriving. No bounce or overshoot except Gradis's own reaction.
- Buttons scale to 0.98 while pressed. Dialogs rise 8px and fade; tooltips rise 2px; menus appear in place. Work in progress shimmers (an agent's live line, a running run's title) and three dots hop while a reply is written.
- Landing reveals: 12px rise and fade, once, staggered 60ms. No parallax, no scroll-progress bar.
- Under `prefers-reduced-motion`, everything appears in its final state.

## Iconography

- Lucide (lucide-react in the app, @lucide/astro on the site), round caps and joins, `currentColor`. The app uses Lucide's default 2px stroke; record tiles and the bundle's `.g-icon` use 1.75.
- 16px in buttons, menus and nav; 14px in compact rows, chat controls and message actions; 12px inside chips; 20px in toasts; 24px in empty states and landing tiles.
- Record kinds in Gradis cards: professor `user-round`, candidate `user-round-search`, programme `book-open`, school `school`, application `clipboard-list`, draft `mail`, run `play`, CV `file-text`. Navigation uses its own set: Gradis `message-circle`, Schools `landmark`, Applications `graduation-cap`, Outbox `mail`, Matches `contact-round`, Documents `file-text`.
- Provider marks (Anthropic, OpenAI, Gemini, Ollama) are their own files under their licences; never recolour them.
- No emoji and no illustrated icons; the only illustration is Gradis.

## Gradis and imagery

Gradis, the penguin in a gold-tasselled cap, is the assistant's face and the only illustration in the product.

- Use the sticker files in the Mascot asset group, never redrawn: in empty and error states (112px, 80px compact) and once on the landing page beside the try-it demo. The app's launcher, bottom-right, is a 72px animated Gradis (the `page-mascot` sprites in `webapp/public/mascots/`) that turns toward the pointer.
- One Gradis per screen. Never on deck slides except the closing "Meet Gradis" slide, never as decoration around content.
- Product imagery is the real interface, built from these components, with real-looking data (named universities, plausible professors). No stock photos of students, no laptops on desks.

## Accessibility

- Text pairs meet 4.5:1 (3:1 at 24px and up) in both themes; control borders, focus rings and meaningful marks meet 3:1. The values are in each token's note.
- Focus is always visible: by default a solid 2px `focus` outline outside a 2px gap; buttons and most app controls draw a flush 2px `focus` ring instead, and list rows an inset one.
- Status never relies on colour: pills carry a word, fit carries a number, the best match carries the words "Best fit", record tones sit beside the kind's word.
- Every icon-only button has an `aria-label` and a tooltip (`data-tooltip`). Hover-only controls (row menus, message actions) also show on keyboard focus, and message actions are always visible on touch screens.

## Using this system

- Tokens: `tokens.css` declares every token as a CSS custom property, light under `:root, [data-theme="light"]` and dark under `[data-theme="dark"], .dark` (the app toggles `.dark` on `<html>`). `tokens.json` carries the same values with usage notes.
- Components: `components/bundle.css` is the framework-free `g-*` layer; both apps load it, and the app's `components/ui/*` render its classes (`g-btn`, `g-pill`, `g-fit`, `g-ecard`, `g-list`, `g-seg`…). Patterns the app draws in Tailwind are documented with `components/app-patterns.css`.
- Tailwind v4: the app maps every token in `@theme inline` (`bg-surface`, `text-label-secondary`, `border-separator`) and re-points Tailwind's own scales at the system; see `webapp/src/index.css` and the README.
- Each component's guidelines name the app file that implements it and what the consumer supplies.

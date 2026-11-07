# Decisions

What the first shipped UI did, what version 2 of this system did instead, and why; then what the app has changed since, which this system now follows. Brand hues (navy `#10325e`, gold `#eda41d`, mist `#e8ecf0`), the logo and Gradis are kept exactly.

| Area | Shipped | Now | Why |
|---|---|---|---|
| Type families | App on the system font; site on Inter with Newsreader titles | Instrument Sans everywhere; Newsreader only for editorial statements (hero, deck, quotes) | Two surfaces looked like two products. One sans gives the app, site and deck one voice; the serif becomes a deliberate, rare moment of academic gravity instead of every h2. |
| Type scale | Ten sizes from 10px, uppercase 11px eyebrows, mono scores | Named roles (`title-2`, `headline`, `callout`…), 12px floor, sentence-case 17px gold eyebrows, tabular sans numerals | Roles say what text is; sizes under 12px failed legibility; uppercase shouting and mono "91.0%" read as a terminal, not a product. |
| Action colour | Navy fill for primary in light, navy-400 in dark | `tint` blue (`#1f57b8` / `#6ea2f5`) for every action; navy moves to text ink and identity fields | Near-black navy buttons read as heavy and compete with text. One clear action hue makes "what can I press" obvious, as a system tint does. |
| Gold | Mixed: saved chips, gradient lines, step lines | The needle: one gold moment per view (Best fit, a deck's key number) plus saved-record chips | Scarcity makes gold mean something. |
| Dark mode | Neutral grey `#191919` page, `#202020` cards, near-white text | Kept as is, completed with neutral steps (`#282828` raised, `#2b2b2b` and `#353535` fills, `#999999` tertiary text) | The neutral greys stay out of content's way; the brand shows through `tint`, `gold` and the logo rather than tinted grounds. |
| Separators | Middle dots between facts ("Carnegie Mellon University · Robotics Institute PhD", run names, usage lines) and em dashes in copy | Commas, line breaks or separate elements; no em dashes unless nothing else works | Dots and dashes add visual noise between every fact; commas read as language, and layout separates the rest. |
| Status colours | Raw Tailwind emerald, amber, red, sky, each varying by screen | Semantic `positive`, `caution`, `critical` with `*-soft` grounds, always with a word | One meaning per colour, checked contrast in both themes, colour-blind safe by the word. |
| Fit score | Green, amber, grey bar; "91.0%" in mono | One hue in three lightnesses; "91%" in tabular sans; band named on detail pages | Fit is a measure, not approval. Green-means-good invited the wrong reading of a 40% match. |
| Record kinds | Five hues (navy, indigo, emerald, sky, rose) for professor, programme, application, draft, school | One neutral icon tile per kind, named in words | Five hues in a chat answer was noise; colour is reserved for status and action. |
| Lists | Bordered rows on the page background | Inset grouped lists: `surface` groups on `canvas`, inset separators | Groups give the eye a container without drawing boxes around every row. |
| Radii | `--radius` 10px with calc multiples, plus 3, 4 and 2xl one-offs | Seven named radii, concentric rule | Nested corners now line up (menu 14 → item 10). |
| Shadows | `shadow-sm` to `shadow-2xl` ad hoc | Three elevations, only for floating things; hairline in dark | Depth now means "on top of", which helps orientation. |
| Tabs and toggles | Tabs, list/grid toggle and range picker styled differently | One SegmentedControl | Same job, same look. |
| Landing hero | Left-aligned sans headline, radial navy glow, blurred gradient behind the demo | Centred serif headline, plain canvas, the product film below | Removes AI-gradient tropes; the product is the hero image. |
| Landing chrome | Four-band progressive frost, scroll-progress gradient line, parallax | One `material` bar; no progress line; no parallax | Fewer effects, more calm; motion is reserved for meaning. |
| How it works | Circles joined by a blue-to-gold gradient line | Four hairline steps with gold numerals | Same information, no decoration. |
| Feature list | Five icon-in-tinted-square items | Bento tiles with live product fragments, one navy trust tile | Show the product doing the thing instead of an icon standing for it. |
| CTAs | 44px rounded rectangles | 52px capsules on marketing; New run capsule in the app | The capsule marks "start something" across surfaces. |
| Empty states | Dashed border box, Gradis 128px | Inside the group surface, Gradis 112px, one action | Dashed borders read as unfinished. |

## Since version 2

The app moved on after the redesign; where it differs, the app is right and the system now documents it.

| Area | Version 2 said | The app does | Notes |
|---|---|---|---|
| Control edges | `control-border` `#7d8899` / `#757575`, 3:1 | `control-border` equals `separator`: inputs, outline buttons, lists and cards have hairline edges | Lighter chrome; focus and hover carry the affordance. |
| Fills | `fill-quiet` `#eef1f5`, `fill` `#e3e8ef` | `#e7eaee`, `#e1e5ed` | A little more contrast for hover and selected rows on white. |
| Resting depth | Lists and cards on `elevation-1` | A 1px `separator` border, no shadow; `elevation-1` (now `0 4px 8px`) on hover and empty states | |
| Lists | Inset separators from the text | Full-width hairlines; rows 56px, 14px titles, 12px subtitles | |
| Record kinds | One neutral tile for every kind | Gradis record cards carry a light tone per kind beside the word and icon | Still never colour alone. |
| Menus | Highlight fills `tint` | Highlight fills `fill-quiet`; a hairline border | |
| Dialogs | `scrim` with blur, 440px, gray and `lg` buttons | Black at 50%, no blur, 512px, a round close button, outline Cancel and a default-size action | |
| Switch | 40×24 with an edge | 36×20, no edge | |
| Sidebar | Six fixed items with run dots, sentence-case groups | New run, search, Gradis, Schools, a Workspace group, collapsible Runs and Chats lists with hover menus; group labels in capitals; resizable | The one uppercase use. |
| Search hint | `.g-kbd` 12px with a ring | 10px, no ring | Below the 12px floor; kept because the app ships it. |
| App chrome | Sticky page header on `material` with `blur-regular` | A 48px top bar with breadcrumbs on `material` with `blur-thin`; list page titles scroll with the page; the run page keeps a sticky header (24px blur, saturate 180%) | |
| Gradis | 56px sticker button, 400px panel | 72px animated launcher; floating, docked or full-page chat | |
| Landing | Pricing teaser section; 56px nav on `blur-regular` | No teaser (pricing has its own page); 64px header on `blur-thin` | |
| Run and draft cards | RunCard and DraftCard tiles | Runs are sidebar rows and the run page; drafts are Outbox rows | Both cards were removed from the system. |

# App guide

How the system appears in the web app (`webapp/src`). Components named here have their own cards.

## Shell

- **Sidebar** (left, `canvas`): logo, New run, search, destinations, the Runs and Chats lists, the account menu. Resizable, collapsible; under 768px a top bar with icons replaces it. See Sidebar and SidebarRow.
- **Top bar**: 48px, translucent (`--app-main-material` with `blur-thin`) with a `separator` bottom edge. Sidebar toggle, breadcrumbs (14px; earlier crumbs `label-secondary` with 14px chevrons), then a health dot, notifications, chat actions and the detail-panel toggle as 28px icon buttons.
- **Main area**: `--app-main`, which is `surface` (white) in light and `canvas` in dark. List pages sit in a 1080px column with 16px gutters (24px from 640px). The new-run page centres a 672px column; the Gradis page gives the chat the whole pane with a 768px column.
- **Detail panel** (right): opens a record without leaving the list. From 1024px it docks beside the content as a card inset 8px (`--app-detail`: `canvas` in light, `surface` in dark; `separator` border; `radius-lg`) with a 48px header (title 14px semibold, open as a page) and a resize handle; narrower, it slides over the page at up to 480px on `scrim`. The row it belongs to stays selected (`tint-soft`).
- **Gradis**: a 72px animated launcher bottom-right opens a floating chat (`canvas`, `separator` border, `radius-xl`, `elevation-3`, resizable from 300×400 to 640×800 by its top-left corner). It can dock as a side panel (on `canvas`, with a `separator` edge) or open as the Gradis page.

## Pages

- **Matches, Schools, Applications, Outbox**: PageHeader (title, search, view toggle, Sort, Filters), then rows in a bordered group (ListRow) or a 12px-gap grid of entity cards. Applications adds a board by status. The Outbox is a list only; a draft opens on its own page, and nothing is ever sent from Graduator: approving marks it reviewed and the applicant copies it into their own mail.
- **Run**: the run's title in `title-2` with its StatusPill, then SegmentedControl tabs per agent type with counts and live badges; tasks show their AgentActivity, and saved records appear as gold RecordChips in the trace.
- **New run**: a centred composer card (`radius-xl`, `separator` border, `elevation-1`, `focus` border while typing) with pill triggers for the run options and a saved statement, and a 32px round send button (see Popover).
- **Gradis**: ChatMessage turns over the Composer; empty chats show a greeting and a carousel of suggestion cards.
- **Documents**: opens in its own tab; a grid of DocumentCards and the editor, where the page is shown as it prints.
- **Settings**: one dialog with a list of panels (Preferences, Data and AI providers, Notifications, Models, Agents and tools, Flows, Usage). Each panel has a 20px title over a description, then bordered sections of rows with Switches, Selects and buttons (see Card).
- **Auth and plans**: a single `surface` card centred on the page; plan cards are bordered panels.

## States

- Loading: skeletons shaped like what they replace (rows, cards, a detail header); small inline waits use a spinning 14 or 16px loader. Never a centred spinner for a page.
- Empty and failed: EmptyState and ErrorState, with the matching Gradis sticker. Inside lists, one `caption` line.
- Live work: a present-tense line that shimmers ("Reading 12 papers by Sergey Levine"), `g-pill--live` on a running run, a shimmering title in the sidebar.
- More to load: lists page in as they scroll (LoadMore).
- Done: a Toast in past tense. Errors that need action: a Banner. Destructive actions confirm in a Dialog that says what will be lost.

## Rules the app follows

- Hover-only controls (row menus, message actions, per-agent controls on tabs) also appear on keyboard focus and stay visible while their menu is open.
- Whole cards and rows are one button or link; inner links and menus sit outside it as siblings, so they never trigger the open.
- Titles in narrow places fade out at the edge instead of ellipsizing when a control may appear over them (sidebar rows); elsewhere they truncate.
- Every icon-only control has `aria-label` and `data-tooltip`.

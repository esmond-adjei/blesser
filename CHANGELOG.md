# Changelog

## Unreleased

## 1.0.0 (2026-10-25)

### Documents editor
- A Docs-style editor: a slim header, tables, a cleaner outline, and suggestions that sit beside the text they change.
- Page-break view shows whole sheets of paper: a half-filled page keeps its full height, with even margins on every page.
- Gradis's own chat lives in the editor's side panel. Select text and "Ask in chat"; the panel resizes from a grip and remembers its width.
- A new document is saved only once something is written; previews stay paper-white in dark mode.

### Gradis
- See a thinking model's thoughts: live while it thinks, then folded under "Thoughts". Works for OpenAI-style reasoning, Claude, Gemini 2.5+ and models that think in `<think>` tags.
- A thinking model that runs out of room is asked again instead of answering "I don't have an answer for that".
- Every chat opens on its latest message, and you can scroll up while a reply streams without being pulled back down.
- The composer fits narrow panels: below a width its controls turn to icons.
- Record cards are drawn and coloured by kind (programme, school, application, draft, candidate, professor, run, CV, suggestions).

### Runs
- The tasks outline sits in the page margin on wide screens, and as a strip under the tabs otherwise; both have tooltips.
- The queue badge in the header links to each active run's task board.
- A run's task list loads each task once: long runs (100+ tasks) no longer refetch forever or show duplicates.
- A tool group with a single call stays folded, since its heading already shows it.

### Professors
- A professor's page shows every paper.

### Marketing site
- The landing page moved out of the web app into `website/`, a separate static site (Astro) deployed to GitHub Pages. Anonymous visitors on the app's root are redirected to it. (#218)
- The site adds what a buyer needs and the app never showed: the sources behind a match, the real product screens, an interactive sample dossier, pricing with a comparison table, and an FAQ.

### CV
- The CV list shows each CV as a portrait card of its real first page, with one "New CV" button and everything else in the card's menu. (#220)
- The editor shows where the PDF's pages break, computed by the same layout that makes the PDF. (#220)
- Download a CV as Word (.docx), with the PDF's page, fonts and structure. (#220)
- Formatting shortcuts: underline (Ctrl/⌘+U) and a link popover (Ctrl/⌘+K) join bold, italic, lists and headings; the command palette moves to Ctrl/⌘+/. (#220)
- A regrouped one-row toolbar, an outline that follows the section you're reading, and fold arrows that appear only on hover. (#220)

### Documents
- The CV page is now Documents: statements of purpose, diversity statements, research proposals, interest statements and notes are written, tailored and reviewed like a CV. "New" starts one of any kind; a filter shows one kind at a time; old `/cv` links still work. Emails stay in the Outbox, linked from the page. (#225)
- Folders, one level deep, to sort documents: create, rename, reorder, delete (its documents stay), and move documents in and out from their menu. (#225)
- Gradis reads and suggests changes to any kind of document (`list_documents`, `read_document`, `suggest_changes`), with the same no-new-facts check; a statement's suggestions are checked against your CVs too. The CV tools keep working for chats that used them. (#225)
- A suggestion whose text was edited since is stale: it's never applied by guessing, only dismissed or replaced with a fresh one asked against the text as it is now. Suggestions that quote text that isn't there aren't kept. (#225)
- A tailored variant remembers the base it was forked from. When the base changes, the variant says "Base updated since fork": see the changes, turn the ones that still fit into suggestions, or keep it as is. The variant's text only changes when you apply one. (#225)
- Word and page limits for any document, or for one variant (a program's own rule). The editor's footer counts words and pages against them and says when it's over; a suggestion that would push the document over is flagged, unless a cut suggested with it makes room. Gradis is held to the same rule. (#225)
- Read-only checks in the editor and for Gradis: leftover placeholders (TODO, [insert …], lorem ipsum), names and dates in a statement that disagree with your CV, and faculty a statement names who aren't among your targets. Click one to see the text; nothing is changed for you. (#225)

## 0.4.0 (2026-10-15)

Accounts, data ownership and production hardening. Every feature built for launch is now on `main`.

### Accounts
- Password reset and email verification. Links are single-use and stored hashed; the mail backend is pluggable. (#57)
- Google sign-in. If the Google email matches an existing account, you confirm with that account's password before the two are linked. (#58)
- Data export: download everything your account owns as one ZIP. Requires a verified email. (#59)
- Usage metering: your own model usage in Settings, and an ops view across accounts. (#60)
- Plans and paywalls, all checked on the server. Off during beta: every account keeps every feature with no limits. (#61)

### Product
- Landing page for signed-out visitors. (#62)
- User-defined agent flows: copy the research pipeline, then switch steps off, narrow tools, or add instructions. (#64)
- CV editor redesign: one workspace with a guided review of suggested changes. (#66)

### Reliability and security
- Fallbacks for external tools: several search providers with a cache, Internet Archive for pages, retries for OpenAlex. (#63)
- CV processing runs in a sandboxed child process with no secrets and with CPU, memory and time limits. (#65)
- Provider API keys are encrypted at rest. Error screens stop one crash from blanking the app. The initial download is 40% smaller (574 KB to 336 KB), and fewer API requests are repeated. (#67)
- Database backups with a verified restore (`make backup`, `make backup-verify`). (#59)

### Docs
- Shorter README; architecture, deployment and per-feature docs in `docs/`. (#68)

### Upgrading
Migrations `020` to `025` run automatically on start. After upgrading:
1. Set `AUTH_SECRET` in production if it isn't set already.
2. Run `make encrypt-secrets` once to encrypt provider keys saved by older versions.
3. Optionally configure SMTP ([docs/email.md](docs/email.md)) and Google sign-in ([docs/sign-in-providers.md](docs/sign-in-providers.md)).

## 0.3.0 (2026-10-15)

First tagged release.

### Features
- Profile name and picture. (#53)
- Shared create and edit run form, and a redesigned New run page. (#51)
- Run interests suggested from your CV. (#52)
- Redesigned add and edit application modal. (#50)
- Create and add actions for Schools and Dossier. (#49)
- One card system for schools, professors, applications and papers. (#48)
- Preview content shown on a flat reading surface. (#47)
- Open-as-page button and a shared preview action menu. (#45)
- Related tools grouped so they toggle together. (#43)
- Gradis: one-tap retry for failed messages (#42); the chat list shows titles and searches message content. (#41)
- Lookups no longer count against run limits, and chat has its own allowance. (#55)

### Security
- Rate limits on uploads and AI endpoints, plus documentation of how LLM data is handled. (#56)
- Deleting an account now removes its uploaded CV files. (#56)
- CV uploads from the UI now send the sign-in token. (#53)

### Fixes
- Closing a fullscreen detail panel no longer freezes the page. (#38)
- The tool selector opens in the right place the first time. (#39)
- The Gradis composer keeps the right height after switching between docked and floating. (#40)
- The loading mascot is centred on every loading screen. (#44)

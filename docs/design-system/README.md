# Graduator Design System

Tokens, components, guidelines, brand assets, fonts and the slide template for the Graduator web app, landing page and pitch deck.

The web app is the source of truth. Where the app and this folder disagree, the app wins and this folder is updated to match.

## Start here

- **See it:** open `gallery/index.html` in a browser. Every component in light and dark, offline.
- **Read it:** `docs/brand-book.md` (principles, voice, colour, type, layout, motion, iconography), then the guides for the app, landing page, pitch deck and entity cards. `docs/01-decisions.md` records what changed from the first shipped UI and why.
- **Use it:** each component's `README.md` names the app file that implements it, the markup, the look and the rules.

## Contents

| Path | What |
|---|---|
| `docs/` | Brand book and guides (decisions, app, landing page, pitch deck, entity cards) |
| `tokens/tokens.css` | Every token as a CSS custom property; dark under `[data-theme="dark"]` or `.dark`; type roles as `.type-<style>`. Synced into the apps. |
| `tokens/tokens.json` | The same tokens with usage notes; `appClass` names the app's class for each interface type role |
| `components/bundle.css` | The `g-*` class layer the apps load (loads the fonts from Google Fonts when used standalone). Synced into the apps. |
| `components/app-patterns.css` | App patterns the web app draws in Tailwind (composer, chat, sidebar rows, popovers, panels…), as `g-*` classes for the gallery. Not synced. |
| `components/<Name>/` | `README.md` guidelines and `preview.html` |
| `gallery/` | Offline previews with a theme switch, built by `gallery.mjs` |
| `assets/logos`, `assets/mascot` | Logo files and Gradis stickers (see each folder's README) |
| `fonts/` | Instrument Sans and Newsreader (variable, for web), static instances for PowerPoint and Keynote, OFL licences |
| `templates/` | PowerPoint template: `.pptx` with sample slides, `.potx` for File > New |

## How the apps get it

`sync.mjs` copies `tokens.css`, `bundle.css` (as `components.css`, without the Google Fonts import) and the web fonts into `webapp/src/styles/design-system/` and `website/src/styles/design-system/`. Each app builds on its own, so each keeps its own copy.

```sh
make design-system                          # write the copies
node docs/design-system/sync.mjs --check    # exit 1 when a copy is stale (CI)
node docs/design-system/gallery.mjs         # rebuild gallery/ from the previews
```

Edit the sources here, never the copies. A change to `tokens.css` or `bundle.css` changes both apps on the next sync.

The web app layers the rest in `webapp/src/index.css`: Tailwind's scales re-pointed at the tokens (`text-sm` is 14px, `rounded-lg` is 14px, `shadow-sm` is `elevation-1`…), every token as a colour utility (`bg-surface`, `text-label-secondary`, `bg-tint-soft`), the shadcn names as aliases (`bg-card` is `surface`, `text-muted-foreground` is `label-secondary`, `bg-accent` is `fill-quiet`, `border-border` is `separator`), the app's type role classes (`.type-page-title`, `.type-meta`, `.type-caption`…) and the shell surfaces (`--app-main`, `--app-detail`). The site does the same in `website/src/styles/global.css`.

## Fonts

Instrument Sans and Newsreader are free under the SIL Open Font License (licences in `fonts/`). The app ships Instrument Sans only; the site ships both. For PowerPoint and Keynote, install the files in `fonts/static-for-office/`.

# Design system

`design-system/` is the npm workspace package `@blesser/ui`: Blesser's tokens, self-hosted fonts and React primitives. The member app uses it today; the admin console and public site will too. The brand book (voice, colour roles, type, shape, motion and the three surfaces) is the [Blesser design system artifact](https://claude.ai/artifact/XfwDvqhmaHGjyVzq3SvAWk). Read it before you add a screen.

## What is where

| Path | What's there |
|---|---|
| `design-system/tokens.json` | The source of truth: colours (light and dark), type styles, spacing, radius, shadows, sizes. Copied from the artifact. |
| `design-system/scripts/build-tokens.mjs` | Generates the two CSS files below. No dependencies. |
| `design-system/src/tokens.css` | Generated. CSS variables: light on `:root`, dark on `.dark` and `[data-theme="dark"]`. |
| `design-system/src/theme.css` | Generated. The Tailwind v4 `@theme` blocks, the `type-*` role utilities, the `dark:` variant and a small base layer. |
| `design-system/src/fonts.css` | Bricolage Grotesque, Figtree and JetBrains Mono from fontsource, bundled with the app (no Google Fonts request). |
| `design-system/src/components/` | Button, Chip, Countdown, Field (with Input, Textarea, Select), OpportunityCard, ApplicationStatus, EmptyState, Logo. |
| `design-system/assets/logos/` | The Path mark as SVG: `blesser-mark.svg`, `blesser-symbol.svg`, `blesser-symbol-white.svg`. |

## Changing tokens

Edit `design-system/tokens.json` (or copy a new version from the artifact), then regenerate and commit the output:

```bash
npm run tokens        # from the repo root
```

The generated CSS is committed so consumers need no build step. Never edit `tokens.css` or `theme.css` by hand.

## Using it in an app

Add the dependency (`"@blesser/ui": "*"`) and list the app in the root `package.json` workspaces, then run `npm install` at the root.

In the app's main stylesheet:

```css
@import "tailwindcss";
@import "@blesser/ui/fonts.css";
@import "@blesser/ui/tokens.css" layer(base);
@import "@blesser/ui/theme.css";
```

`theme.css` carries `@source "./components"`, so Tailwind picks up the classes the package components use. The package exports TypeScript sources; Vite compiles them, no build step needed.

```tsx
import { Button, Countdown, EmptyState, OpportunityCard, buttonVariants, daysUntil } from "@blesser/ui"

<Button variant="primary" icon={<Plus />}>Track</Button>
<a href={url} className={buttonVariants({ variant: "secondary", size: "sm" })}>Official page</a>
<Countdown daysLeft={daysUntil("2026-11-21")} date="2026-11-21" />
<Countdown variant="text" daysLeft={12} />   // no fill, for rows in dense lists
```

Dark mode follows a `dark` class (or `data-theme="dark"`) on `<html>`. The member app sets it from `prefers-color-scheme` in `index.html`; do the same, or toggle it yourself.

## Utilities

- Colours by role: `bg-canvas`, `bg-surface`, `bg-surface-sunk`, `text-ink`, `text-ink-secondary`, `bg-sun text-on-sun`, `bg-forest text-on-forest`, `bg-sun-soft text-sun-ink`, `text-link`, `outline-focus`, and the rest of `tokens.json`.
- Type: `type-hero`, `type-title-1`, `type-title-2`, `type-numeral` (display face) and `type-title-3` to `type-code`; or size-only `text-callout`, `text-footnote` and friends.
- Shape and depth: `rounded-sm` 8px (inputs), `rounded-lg` 20px (cards, dialogs), `rounded-xl` 28px (site bands), `rounded-full` for anything pressable; `shadow-elevation-1/2/3`.
- Sizes: `h-control-sm/md/lg` (32, 40, 48px), `max-w-content`, `max-w-reading`.
- `cn()` from the package merges classes and knows these names; use it instead of a local `tailwind-merge` setup.

## Rules worth repeating

- One sun (`primary`) button per view. Forest (`brand`) when the page already has one.
- Deadlines always show as a `Countdown`; never red. Use the default pill on cards and detail pages and `variant="text"` in lists and tables, where urgency shows only in the text colour. Rejections read "Not this time".
- A pressed `Chip` is a soft forest tint with a forest outline, not a solid fill.
- In the member app, keep colour for meaning: page titles are 20px, lists are bordered rows without shadows, and status is a small dot plus a word rather than a filled badge.
- Empty lists use `EmptyState`. Pass `illustration` (an image src, e.g. `/illustrations/…` in the app's `public/`) to replace the sunrise.

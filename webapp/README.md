# Graduator web app

The Graduator dashboard, built with React 19, TypeScript, Vite and Tailwind CSS 4.

## Run it

The API must be running on `localhost:8000` (see [`api/README.md`](../api/README.md)). Run the worker as well if you want runs to make progress.

```bash
npm install
npm run dev        # http://localhost:5173
```

The dev server forwards `/api`, `/health` and `/ready` to `localhost:8000`. To use an API on another host, set `VITE_API_URL` in `.env` (copy it from `.env.example`).

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Type-check (`tsc -b`) and build to `dist/` |
| `npm run lint` | oxlint (CI runs this) |
| `npm test` | Vitest (not yet in CI) |
| `npm run preview` | Serve the production build locally |

## Stack

- **Routing:** React Router
- **Server state:** TanStack Query. Live updates arrive over server-sent events (`lib/live.ts`) and refresh the matching queries.
- **UI:** shadcn-style primitives in `components/ui/`, lucide icons, sonner toasts
- **Markdown:** react-markdown with remark-gfm, styled by the `.rich-text` type role

## Layout

```
src/
  App.tsx          routes (signed-out visitors go to the marketing site via `VITE_SITE_URL`, else sign-in)
  pages/           one component per route
  components/
    ui/            primitives: button, dialog, menu, combobox, tabs...
    layout/        app shell, sidebar, breadcrumbs, detail panel
    cards/         shared item cards (schools, professors, applications)
    listing/       list and grid views with search, sort and filters
    gradis/        the Gradis chat assistant
    documents/     document editor (CVs, statements) and list
    auth/          third-party sign-in buttons (Google)
    billing/       upgrade prompt, shown when the API returns 402
    run/ dossier/ outbox/ schools/ applications/ settings/ dialogs/ feedback/ entity/ filters/ lists/
  lib/
    api.ts         typed client for every backend route
    queries.ts     TanStack Query hooks
    auth.tsx       session and token refresh
    types.ts       API types
public/
  mascot-states/   Gradis stickers for empty, loading and error states
```

## Conventions

- Drafts are never sent. Approving one only marks it as reviewed; you copy it into your own mail client.
- Colours come from the theme tokens in `index.css`, so light and dark mode both work. Don't hard-code colours.
- Text sizes come from the type scale in `index.css`: use the named steps (`text-2xs`, `text-compact`, `text-md`, …) instead of arbitrary values, and the roles (`type-page-title`, `type-panel-title`, `type-section-title`, `type-eyebrow`, `type-meta`, `type-caption`) instead of repeating size + colour utilities.
- Paragraphs inherit the size of their surface. A compact surface (the rail, a card, chat) sets `text-sm` once at its root; long-form Markdown is wrapped in `.rich-text` and always matches the text around it.
- Empty, loading and error states use `EmptyState` / `LoadingScreen` with a Gradis sticker.

## Production

`Dockerfile` builds the app and serves `dist/` with nginx (`nginx.conf`). Leave `VITE_API_URL` empty to forward `/api` to the API container on the same origin, or set it at build time to point at a separate API host. See [docs/deployment.md](../docs/deployment.md).

# Blesser web app

React 19, TypeScript, Vite and Tailwind CSS 4. Needs Node 26 (see the root `.nvmrc`).

## Run it

The API must be running on `localhost:8000` (see [`api/README.md`](../api/README.md)); run the worker too if you want scans to make progress.

The app is an npm workspace with `design-system/` (`@blesser/ui`), so install from the repo root:

```bash
npm install                      # at the repo root
npm run --workspace webapp dev   # http://localhost:5173
```

The dev server forwards `/api` and `/ready` to `localhost:8000`; the app calls the member routes under `/api/app`. To use an API on another host, set `VITE_API_URL` in `.env` (copy it from `.env.example`).

Every page needs an account. A signed-out visit to `/` goes to the public site at `VITE_SITE_URL` (unset: `http://localhost:4321`; empty: `/login`). `/register?track=<slug>` and `/login?track=<slug>` track that opportunity once the visitor is signed in and open Applications.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Type-check (`tsc -b`) and build to `dist/` |
| `npm run lint` | oxlint |
| `npm test` | Vitest |
| `npm run preview` | Serve the production build locally |

## Layout

| Path | What's there |
|---|---|
| `src/pages/` | One file per screen: Opportunities, Applications, Todos, Scans, Settings, Auth, Legal |
| `src/components/` | `ui/` (dialog, tooltip, skeleton and alert), `layout/` (the shell), `feedback/`, `settings/` (notification settings) |
| `src/lib/` | `api.ts` (typed fetch client), `auth.tsx` (session), `opportunities.ts` and `applications.ts` (query hooks and labels), `push.ts` (browser push), `track.ts` (`?track=` after sign-up or sign-in), `site.ts` (public site URL) |

Buttons, chips, countdowns, fields, cards, statuses, empty states and the logo come from `@blesser/ui`; see [`docs/design-system.md`](../docs/design-system.md).

Server state lives in TanStack Query; a running scan's page polls every few seconds.

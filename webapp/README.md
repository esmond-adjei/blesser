# Blesser web app

React 19, TypeScript, Vite and Tailwind CSS 4. Needs Node 26 (see `.nvmrc`).

## Run it

The API must be running on `localhost:8000` (see [`api/README.md`](../api/README.md)); run the worker too if you want scans to make progress.

```bash
npm install
npm run dev        # http://localhost:5173
```

The dev server forwards `/api` and `/ready` to `localhost:8000`. To use an API on another host, set `VITE_API_URL` in `.env` (copy it from `.env.example`).

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
| `src/pages/` | One file per screen: Opportunities (public), Applications, Todos, Scans, Settings, Auth, Legal |
| `src/components/` | `ui/` primitives, `layout/` (the shell and logo), `feedback/`, `settings/` (notification settings) |
| `src/lib/` | `api.ts` (typed fetch client), `auth.tsx` (session), `opportunities.ts` and `applications.ts` (query hooks and labels), `push.ts` (browser push) |
| `src/styles/design-system/` | Tokens, component classes and fonts |

Server state lives in TanStack Query; a running scan's page polls every few seconds.

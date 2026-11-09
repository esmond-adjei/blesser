# Blesser public site

The public website (`blesser.org`): Astro, server-rendered by the Node adapter, styled with `@blesser/ui`. It reads only `/api/public/*` (see `docs/api-contract.md`) and ships no client JavaScript.

```bash
npm run -w site dev      # http://localhost:4321, from the repo root
npm run -w site build    # astro check + astro build
node site/dist/server/entry.mjs
```

## Environment (read at request time)

| Variable | Default | Use |
|---|---|---|
| `API_INTERNAL_URL` | `http://localhost:8000` | Where server-side fetches reach the API (`http://api:8000` in compose). |
| `PUBLIC_APP_URL` | `http://localhost:5173` | Member app origin for "Track" (`/register?track=<slug>`), "Create account" and "Sign in". |
| `SITE_URL` | `http://localhost:4321` | Public origin for canonical URLs, Open Graph, `sitemap.xml` and `robots.txt`. |
| `CONTACT_EMAIL` | empty | Shown on the privacy page. |
| `HOST`, `PORT` | `0.0.0.0`, `4321` in the image | Listen address. |

Pages send `Cache-Control: public, s-maxage=300, stale-while-revalidate=3600`; API failures render a friendly section with status 503. The calendar link points at `/api/public/opportunities/<slug>/calendar.ics` on the same host; in production nginx sends `/api` to the API, elsewhere the site proxies that one route itself.

## Docker

```bash
docker build -f site/Dockerfile -t blesser-site .   # from the repo root
```

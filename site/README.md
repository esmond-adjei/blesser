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

## GitHub Pages (static snapshot)

`.github/workflows/pages.yml` builds with `SITE_STATIC=1` and `SITE_BASE=/blesser`: every page is prerendered from the API at build time, and the workflow reruns daily. Listings filter and page in the browser; share pages (`/s/*`) and share images aren't built. Set the repo variables `BLESSER_API_URL` (public API origin), `BLESSER_APP_URL` and optionally `BLESSER_CONTACT_EMAIL`. If the API can't be reached, the site still builds without its listing sections.

```bash
SITE_STATIC=1 SITE_BASE=/blesser SITE_URL=https://esmond-adjei.github.io/blesser npm run -w site build
```

## Docker

```bash
docker build -f site/Dockerfile -t blesser-site .   # from the repo root
```

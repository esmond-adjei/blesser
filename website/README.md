# The marketing site

A separate static site for Graduator. Its job is to explain the product and send people
into the app.

- **Stack:** Astro 7 (static output), Tailwind 4, no UI framework. The page
  uses browser JavaScript for interactive content and live pricing.
- **Brand:** the same tokens as the app (`src/styles/global.css`), so the
  two surfaces look like one product.

## Commands

```bash
npm install
npm run dev       # dev server on :4321
npm run build     # static build into dist/
npm run preview   # serve the build
npm run check     # astro check (types)
```

From the repo root: `make site`, `make site-build`, `make site-preview`.

## Configuration

Build-time variables, all public (see `.env.example`):

| Variable | What it is |
|---|---|
| `PUBLIC_SITE_URL` | This site's origin. Canonical links, sitemap, `robots.txt`. |
| `PUBLIC_APP_URL` | Where calls to action point: the app. |
| `PUBLIC_API_URL` | Backend API base for live pricing, including `/api`. Defaults to `PUBLIC_APP_URL/api`. |
| `PUBLIC_CONTACT_EMAIL` | Address for privacy and removal requests. |
| `BASE_PATH` | Only for a Pages *project* site on a subpath (e.g. `/graduator`). |

The webapp has the mirror image of this: `VITE_SITE_URL` sends anonymous
visitors on the app's root to the site.

## Layout

```
src/
  layouts/Base.astro     the html shell: meta, Open Graph, JSON-LD, header, footer
  components/            header, footer, and one component per section
  components/sections/   the home page, section by section
  lib/site.ts            the URLs every link is built from
  lib/plans.ts           public pricing catalog client and response validation
  lib/faq.ts             the questions, shared by the home page and /faq
  pages/                 index, pricing, faq, privacy, terms, 404, robots.txt
public/                  favicon, social card, mascot
scripts/                 build the logo, favicon and social card from the app's assets
```

## Editing

- **Copy:** the sections are plain `.astro` files with the words inline. The
  FAQ lives in `src/lib/faq.ts` so the home page and `/faq` cannot drift.
- **Legal pages:** `src/pages/privacy.astro` and `terms.astro` mirror the
  app's notices. Change the wording in both places, and keep the version
  stamp in step with the app's `TERMS_VERSION`.
- **Logo, favicon and social card:** all three are generated from the app's
  own assets, so the brand cannot drift. After changing
  `webapp/src/components/layout/AppLogo.tsx` or `webapp/public/logo-*.svg`,
  run:

  ```bash
  node scripts/build-logo.mjs
  node scripts/build-favicon.mjs
  node scripts/build-og.mjs
  ```

- **Plans:** edit `api/api/billing/plans.py`, the same definitions used by checkout.
  `/pricing` fetches `GET /api/billing/catalog` on page load. Prices, quotas,
  feature comparisons, welcome credits and top-ups come from that public endpoint.
  There is no local price fallback. A failed request shows a retry button.
  Deploy the backend endpoint before the website. Set `PUBLIC_API_URL` in the
  Pages repository variables if the API has a separate origin, and include the
  marketing origin in the backend's `CORS_ORIGINS`. No login or cookies are needed.
  Backend plan changes appear on the next page load without rebuilding the site.
- **Product film:** the home page's video is drawn by
  `scripts/video/scene.html` (open it in a browser to watch it play) and
  rendered frame by frame into `public/media/`. After changing the scene,
  run (needs GStreamer with `vp9enc`, `openh264enc` and `mp4mux`; about
  three minutes):

  ```bash
  node scripts/build-video.mjs
  ```

  If you change what happens in it, update the caption under the video in
  `src/components/FilmPlayer.astro` to match.

  An alternative film, a recording of the real app from an invented demo
  account, is kept unused as `public/media/graduator-app-film.*`. Rebuild
  it with the dev API and webapp running:
  `CHROME=/usr/bin/google-chrome node scripts/build-app-film.mjs`.

## Deploying

`.github/workflows/pages.yml` builds and publishes on every push to `main`
that touches `website/`. It needs repository variables; see
[docs/deployment.md](../docs/deployment.md#the-marketing-site).

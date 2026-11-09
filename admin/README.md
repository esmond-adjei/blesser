# Blesser admin

React 19, TypeScript, Vite, TanStack Query, React Router and `@blesser/ui`. The binding API contract is [`docs/api-contract.md`](../docs/api-contract.md).

Run these commands from the repository root. Use the already installed workspace dependencies.

```sh
npm run -w admin dev
npm run -w admin lint
npm run -w admin test
npm run -w admin build
```

The development server listens on port 5174 and proxies `/api` to `http://localhost:8000`. Production uses the same origin unless `VITE_API_URL` is set at build time. Use a verified editor or admin account. Access tokens stay in memory. Refresh tokens use `blesser.admin.refresh_token` in local storage, separate from the member app.

Review queue shortcuts work outside inputs and pause during confirmations, edits and pending writes. Use `j` or `k` to move, `p` to approve to public, `m` to approve to members, `h` to open the hide confirmation, and `e` to edit. Filters and open listings have shareable URLs.

The Docker build context is the repository root:

```sh
docker build -f admin/Dockerfile -t blesser-admin .
```

The nginx configuration forwards API requests to the `api:8000` service and serves the SPA for direct route visits.

## Browser verification

The dependency-free browser smoke script uses Chrome's DevTools protocol through Node's built-in WebSocket client. Start the app and a dedicated Chrome instance, then run:

```sh
google-chrome --headless=new --no-sandbox --remote-debugging-port=9234 --user-data-dir=/tmp/blesser-admin-smoke about:blank
node admin/scripts/browser-smoke.mjs
```

For the production bundle, run `npm run -w admin preview -- --host 127.0.0.1 --port 4174`, then:

```sh
ADMIN_SMOKE_URL=http://127.0.0.1:4174 node admin/scripts/browser-smoke.mjs
```

The script intercepts admin API requests with contract fixtures. It checks actual rendered screens and interactions, including publishing, creation and editing, collection CRUD, featured ordering, scans, reports, access changes, audit diffs, settings, role guards, and merge and re-verification confirmations. It saves screenshots and a request log under `admin/.agent-logs/`. Fixture checks do not prove live backend integration.

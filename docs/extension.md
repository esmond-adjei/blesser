# Browser extension: Apply with Blesser

The extension fills application forms from a member's Apply kit (profile, projects, documents, saved answers). It fills and highlights; the member reviews and submits. Chrome and Edge, Manifest V3. The plan is `docs/plans/sharing-and-autofill.md` (sections 3 and 4).

## Layout

| Path | What |
|---|---|
| `extension/src/content/` | Content script. `collect.ts` reads fields, `fill.ts` writes values, `highlight.ts` draws outlines and tags. Pure DOM code, tested under jsdom. |
| `extension/src/background/` | Service worker. Holds tokens, makes every API call, injects the content script, downloads documents. |
| `extension/src/popup/`, `src/options/` | React pages styled with `@blesser/ui` tokens; they follow the OS light or dark theme. |
| `extension/manifest.config.ts` | Builds `manifest.json` from the build environment. |
| `extension/test/` | Unit tests with fixture forms (Google Forms, Greenhouse, Lever, Workable, Submittable, a plain grant form) and a React-controlled form. |
| `extension/e2e/run.mjs` | End-to-end check in real Chromium. |
| `webapp/src/pages/ConnectExtension.tsx` | The `/connect/extension` page in the member app. |
| `webapp/src/components/settings/ConnectedBrowsers.tsx` | Settings, Account and security: connected browsers with Disconnect. |

## Build

```sh
npm install
npm -w extension run build          # or: make extension
```

Output goes to `extension/dist/`. The build reads:

| Variable | Default | Use |
|---|---|---|
| `BLESSER_API_URL` | `http://localhost:8000` | Default API address (changeable in the options page). |
| `BLESSER_APP_URL` | `http://localhost:5173` | Default member app address; its origin is allowed to hand tokens to the extension. |
| `BLESSER_APP_ORIGINS` | none | Extra app origins for `externally_connectable`, comma separated (e.g. staging). |
| `BLESSER_OUT_DIR` | `dist` | Output folder. |
| `BLESSER_E2E_HOSTS` | none | Test builds only: adds `host_permissions`, since automation can't press the toolbar button that grants `activeTab`. Never set it for a release. |

A production build: `BLESSER_API_URL=https://api.example BLESSER_APP_URL=https://app.example npm -w extension run build`.

`externally_connectable` is fixed at build time, so an app address entered in the options page only works for connecting if its origin was in the build. The options page warns when it isn't.

## Load it unpacked

1. Open `chrome://extensions` (Edge: `edge://extensions`) and turn on Developer mode.
2. Load unpacked, and pick `extension/dist`.
3. Pin "Blesser" to the toolbar.

After a rebuild, press the reload icon on the extension's card. Run `npm -w extension run dev` to rebuild the popup, options page and service worker on save (rebuild the content script with `npx vite build -c vite.content.config.ts`).

## Connect

1. Popup, **Connect to Blesser**. The service worker makes a random `state`, keeps it for 10 minutes, and opens `{APP_URL}/connect/extension?ext={extension id}&state=…`.
2. Signed-out members go through sign-in (`/login?next=…`) and come back.
3. The page lists what the extension can use. **Allow** calls `POST /api/app/extension/connect` with a browser name ("Chrome on Linux") and sends `{type: "blesser.connect", state, access_token, refresh_token, session}` with `chrome.runtime.sendMessage(ext, …)`.
4. The service worker accepts it only from the configured app origin and only for the state it issued (single use). If the hand-off fails, the page revokes the new session at once.

Tokens live in `chrome.storage.local`, which content scripts can't read. On a 401 the service worker refreshes once through `POST /api/app/extension/refresh` (single flight, rotated tokens saved); if the refresh is refused it signs out. Disconnect in the popup calls `/extension/logout`; Disconnect in Settings revokes the session server-side.

The API must allow the extension's origin in CORS (`CORS_ORIGINS=*` in dev, or add `chrome-extension://<id>` in production).

## Filling

**Fill this page** injects `content.js` into all frames of the active tab, collects fields, sends one `FillRequest` (fields keyed `frameId:index`), downloads any documents the response names, and fills frame by frame. The popup then shows filled, drafted for review and "need you", with jump-to for each unfilled field, and **Mark as applied** when `matched_opportunity_id` points at a tracked application (it finds the application with that `opportunity_id` and sends `PATCH /api/app/applications/{id}` with `{status: "submitted"}`).

Collection reads labels from `aria-labelledby`, `<label for>`, wrapping labels (minus the branch that holds the control), `aria-label`, then the question text around the field; help text from `aria-describedby` and nearby text; sections from fieldset legends or the nearest heading; options for selects, radio and checkbox groups; required flags (`required`, `aria-required`, `*`, `✱`); `maxlength`; word limits from the text ("max 200 words", "(300 words max)", "up to 80 words").

Filling writes through the native value setter and fires `focus`, `input`, `change` and `blur`, so React, Vue and Angular see the change. Selects and options match by value, then label, then a single unambiguous partial match. Dates are converted to the input's format. Rich text editors get `insertText`, falling back to text plus an `input` event. Files are built from the downloaded document and attached with `DataTransfer`, after checking `accept`. Filled fields get a green outline; drafted ones a dashed amber outline and a "Drafted by Blesser, review" tag drawn in an overlay (shadow DOM), so page markup isn't touched. Fields the member already typed in are left alone; a second Fill refreshes only Blesser's own values.

## What it never does

- Never submits a form and never clicks buttons or links. The only synthetic click is on a radio or checkbox input being set, which is how the browser selects it and how React registers it.
- Never collects or fills password, one-time code or payment fields (card, CVV, IBAN, account and routing numbers, `cc-*` autocomplete).
- Never reads a page until the member presses Fill. Permissions are `activeTab`, `scripting` and `storage`; there are no host permissions.
- Never operates custom ARIA widgets (Google Forms choices, react-select): they appear under "need you" with the suggested answer.
- Never stores what it filled. The API keeps only a usage counter.

## Tests

```sh
npm -w extension run lint
npm -w extension test
npm -w extension run build
```

End to end (real Chromium with the unpacked extension, real API and member app):

```sh
# your own API, console mail, never one that loads real SMTP for throwaway accounts
cd api && MAIL_BACKEND=console APP_BASE_URL=http://localhost:5180 uv run uvicorn api.main:app --port 8010
API_PROXY_TARGET=http://localhost:8010 npm -w webapp run dev -- --port 5180
E2E_DRAFTING=0 E2E_SCREENSHOTS=/tmp/ext-shots npm -w extension run e2e
```

It registers a throwaway account, seeds a profile, the project "Siwa" and a CV, connects through `/connect/extension`, fills `e2e/site/form.html` (including a same-origin frame) as Siwa, checks the card field stayed empty and the form wasn't submitted, checks Settings lists the browser, then deletes the account. `E2E_DRAFTING=0` turns drafting off so the run doesn't depend on the model.

## Known limits

- Cross-origin frames: `activeTab` covers the tab's own origin, so embedded forms from another origin are skipped.
- CAPTCHA, fully custom widgets that ignore input events, and ARIA-only choice widgets (left for the member).
- One question per screen flows (Typeform style) and multi-page forms: press Fill on each screen.
- `externally_connectable` origins are set at build time.
- Drafting waits on the model; the extension gives up after 75 seconds with a message suggesting drafting off.
- Firefox is Phase 5.

## Store submission checklist

- [ ] Release build with production `BLESSER_API_URL` and `BLESSER_APP_URL`; no `BLESSER_E2E_HOSTS`; check `dist/manifest.json` has no `host_permissions`.
- [ ] Bump `version` in `extension/package.json`; zip the contents of `extension/dist`.
- [ ] API `CORS_ORIGINS` includes `chrome-extension://<store id>` (and the Edge id).
- [ ] Privacy policy URL covering the Apply kit and the extension (the site's privacy page section from the plan).
- [ ] Permission justifications: `activeTab` (read and fill the form the member asked to fill), `scripting` (inject the filler on demand), `storage` (sign-in tokens and settings).
- [ ] Data disclosure: personal info, documents and form field descriptions are sent to Blesser to produce answers; not sold, not used for ads, not shared beyond the configured model for drafting.
- [ ] Single purpose statement: fill application forms from the member's Blesser Apply kit.
- [ ] Screenshots (1280x800) of the popup results and a filled form; 128 px icon (`public/icons/128.png`); store name (working: "Blesser: Apply with your kit").
- [ ] Edge Add-ons: same zip, separate listing; add the Edge extension id to CORS.
- [ ] Test the store build against production: connect, fill, Mark as applied, disconnect from Settings.

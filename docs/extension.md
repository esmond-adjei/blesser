# Browser extension: Apply with Blesser

The extension fills application forms from a member's Apply kit (profile, projects, documents, saved answers). It fills and highlights; the member reviews and submits. Chrome and Edge, Manifest V3. The plan is `docs/plans/sharing-and-autofill.md` (sections 3 and 4).

## Layout

| Path | What |
|---|---|
| `extension/src/content/` | Content script. `collect.ts` reads fields, `fill.ts` writes values (fills and in-place edits), `watch.ts` notices member edits and new form steps, `highlight.ts` draws outlines and tags. Pure DOM code, tested under jsdom. |
| `extension/src/background/` | Service worker. Holds tokens, makes every API call, injects the content script, downloads documents, keeps each tab's review (`actions.ts`). |
| `extension/src/shared/review.ts` | The review list state: grouping, edits, clears, wrong field, page edits, plain-words sources and feedback payloads. |
| `extension/src/sidepanel/`, `src/options/` | React pages styled with `@blesser/ui` tokens; they follow the OS light or dark theme. |
| `extension/manifest.config.ts` | Builds `manifest.json` from the build environment. |
| `extension/test/` | Unit tests with fixture forms (Google Forms, Greenhouse, Lever, Workable, Submittable, a plain grant form) and a React-controlled form. |
| `extension/e2e/run.mjs` | End-to-end check in real Chromium. |
| `webapp/src/pages/ConnectExtension.tsx` | The `/connect/extension` page in the member app. |
| `webapp/src/components/settings/ConnectedBrowsers.tsx` | Settings, Account and security: connected browsers with Disconnect. |
| `webapp/src/pages/kit/CorrectionsTab.tsx` | Apply kit, Corrections: what the extension remembered, by site, with delete. |

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
3. Pin "Blesser" to the toolbar. Pressing it opens the Blesser side panel (Chrome and Edge 116+).

After a rebuild, press the reload icon on the extension's card. Run `npm -w extension run dev` to rebuild the side panel, options page and service worker on save (rebuild the content script with `npx vite build -c vite.content.config.ts`).

## Connect

1. Side panel, **Connect to Blesser**. The service worker makes a random `state`, keeps it for 10 minutes, and opens `{APP_URL}/connect/extension?ext={extension id}&state=…`.
2. Signed-out members go through sign-in (`/login?next=…`) and come back.
3. The page lists what the extension can use. **Allow** calls `POST /api/app/extension/connect` with a browser name ("Chrome on Linux") and sends `{type: "blesser.connect", state, access_token, refresh_token, session}` with `chrome.runtime.sendMessage(ext, …)`.
4. The service worker accepts it only from the configured app origin and only for the state it issued (single use). If the hand-off fails, the page revokes the new session at once.

Tokens live in `chrome.storage.local`, which content scripts can't read. On a 401 the service worker refreshes once through `POST /api/app/extension/refresh` (single flight, rotated tokens saved); if the refresh is refused it signs out. Disconnect in the side panel calls `/extension/logout`; Disconnect in Settings revokes the session server-side.

The API must allow the extension's origin in CORS (`CORS_ORIGINS=*` in dev, or add `chrome-extension://<id>` in production).

## The side panel

The toolbar button opens Chrome's side panel (`chrome.sidePanel`, `setPanelBehavior({openPanelOnActionClick: true})`); there is no popup. The panel stays open while the member moves between tabs, pages and form steps, and always works on the active tab of its window. It holds: who it fills as (Me or a project), the drafting switch, **Fill this page**, and the review list for that tab, plus **Mark as applied** and **Report a problem**.

## Filling

**Fill this page** injects `content.js` into all frames of the active tab, collects fields, sends one `FillRequest` (fields keyed `frameId:index`), downloads any documents the response names, and fills frame by frame. The service worker stores the result as the tab's review (`chrome.storage.session`, `review:<tabId>`); the panel renders it and re-renders whenever it changes, so actions and page events update one copy.

### Review list

Grouped as **Filled**, **Drafted** and **Needs you**. Each row shows the field label, the value (option labels, not codes; a document's file name), and where it came from in plain words, built from the fill's `source`, `rule` and `note`:

| Rule | Shown as |
|---|---|
| `inferred:nationality` | From your nationality (with "Medium confidence") |
| `concept:gender` | the note when it reads "Matched 'Male' to 'Man'", else "Matched your gender to 'Man'" |
| `qualifier:education.country` | From your education: country |
| `correction` | Your earlier correction |
| `model:choice` | Chosen by Blesser, review |
| none, `source: drafted` | Drafted by Blesser, review |

Medium and low confidence show as a quiet "Medium confidence" tag; high shows nothing. Open a row (click, or Enter on it) for its actions:

- **Jump to field** scrolls to the field and flashes it.
- **Edit** (or **Fill in** for Needs you) opens an editor fitted to the field: a dropdown of the form's own options for selects and radios, checkboxes for multi-choice, Yes/No for a single checkbox, a text area with the word count for long answers. **Save to page** (Ctrl/Cmd+Enter; Escape cancels) writes through the same native setter and `focus`/`input`/`change`/`blur` events as filling, reads the value back, and sends feedback.
- **Clear** empties the field on the page. No feedback.
- **Wrong field** empties it and sends feedback with `{wrong_field: true}`, so Blesser leaves that field alone on that site.

Feedback is `POST /api/app/autofill/feedback` with `{page: {url, host}, field, filled: {value, source, rule}, corrected}` (`filled.source` is `"unfilled"` for a Needs you row). `page.host` is the URL's hostname without a port, which is what the API checks. If feedback fails, the page keeps the change and the row says Blesser couldn't remember it.

### Following the page

- **Navigation.** The service worker listens to `tabs.onUpdated`; when the reviewed tab starts loading, the review is marked "navigated" and the panel offers **Fill this step**, with the old list kept below (its page actions disabled).
- **New steps on the same page.** After a fill, the content script runs a `MutationObserver` (childList plus `hidden`, `style`, `class`, `aria-hidden`), debounced; when fields appear that weren't there, it reports `blesser.step` and the panel offers **Fill this step**.
- **Member edits.** The content script listens to trusted `input` and `change` events on fields Blesser filled (Blesser's own writes are untrusted events, so they never count). When the value settles and differs from what the panel shows, the row offers **Remember this correction** (sends feedback) or **Just this once**.

Content scripts can only report these two page events to the service worker; every action comes from the extension's own pages. Nothing is watched before the member presses Fill, and nothing survives a page load.

### Report a problem

Opt-in, one report at a time: the dialog collects the page's field descriptors fresh, shows how many fields and from which site (with **See what's sent** listing labels and types), and needs a note. **Send report** posts `{page: {url, host, title}, fields, note}` to `POST /api/app/autofill/reports`. Descriptors are rebuilt key by key before sending, so values never go, even if something added them.

### Mark as applied

Shown when `matched_opportunity_id` points at a tracked application: it finds the application with that `opportunity_id` and sends `PATCH /api/app/applications/{id}` with `{status: "submitted"}`.

### Corrections in the Apply kit

Apply kit, **Corrections** (`/kit/corrections`) lists `GET /api/app/autofill/corrections` grouped by site: label, the remembered value or "Wrong field", field type and when. The bin calls `DELETE /api/app/autofill/corrections/{id}`. The profile's Identity section has **Country of birth** and **Place of birth**; when country of birth is empty the matcher infers it from nationality at medium confidence.

Collection reads labels from `aria-labelledby`, `<label for>`, wrapping labels (minus the branch that holds the control), `aria-label`, then the question text around the field; help text from `aria-describedby` and nearby text; sections from fieldset legends or the nearest heading; options for selects, radio and checkbox groups; required flags (`required`, `aria-required`, `*`, `✱`); `maxlength`; word limits from the text ("max 200 words", "(300 words max)", "up to 80 words").

Filling writes through the native value setter and fires `focus`, `input`, `change` and `blur`, so React, Vue and Angular see the change. Selects and options match by value, then label, then a single unambiguous partial match. Dates are converted to the input's format. Rich text editors get `insertText`, falling back to text plus an `input` event. Files are built from the downloaded document and attached with `DataTransfer`, after checking `accept`. Filled fields get a green outline; drafted ones a dashed amber outline and a "Drafted by Blesser, review" tag drawn in an overlay (shadow DOM), so page markup isn't touched. Fields the member already typed in are left alone; a second Fill refreshes only Blesser's own values.

## What it never does

- Never submits a form and never clicks buttons or links. The only synthetic click is on a radio or checkbox input being set, which is how the browser selects it and how React registers it.
- Never collects or fills password, one-time code or payment fields (card, CVV, IBAN, account and routing numbers, `cc-*` autocomplete).
- Never reads a page until the member presses Fill. Permissions are `activeTab`, `scripting`, `storage`, `sidePanel` and `contextMenus`; host access is optional (`https://*/*`, `http://*/*`) and only requested when the member presses **Allow on all sites**, and `tabs.onUpdated` is used without the `tabs` permission (it only needs to know a load started).
- Never sends values in a problem report: field descriptors and the member's note only.
- Never operates custom ARIA widgets (Google Forms choices, react-select): they appear under "need you" with the suggested answer.
- Never stores what it filled. The API keeps a usage counter, and the corrections the member chose to send (edits, "Wrong field", "Remember this correction"), which the member can delete in the Apply kit.

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

Automation can't open Chrome's side panel, so the run checks the manifest (`side_panel`, no `default_popup`, the `sidePanel` permission) and that `getPanelBehavior()` has `openPanelOnActionClick`, then opens the panel page itself in a tab: `chrome-extension://<id>/sidepanel.html?tab=<form tab id>`. Test builds (`BLESSER_E2E_HOSTS`) honour `?tab=` and bind the panel to that tab; release builds ignore it.

It registers a throwaway account, seeds a profile (gender "Male", nationality "Ghanaian", an education entry in Ghana), the project "Siwa" and a CV, connects through `/connect/extension`, then:

1. fills `e2e/site/form.html` (with a same-origin frame) as Siwa; the card field stays empty and the form isn't submitted;
2. edits First name in place, marks Phone as the wrong field, types into Last name on the page and remembers it, checking each feedback payload;
3. adds fields to the page and expects **Fill this step**; sends a report and checks it carries no values;
4. navigates to `step2.html`, expects **Fill this step**, and fills it;
5. fills `v2.html` as Me, the owner's failure cases: Gender "Male" must pick "Man", Country of birth must be "Ghana" from "Ghanaian", Country of institution must be the education entry's country, and First name must reuse the earlier correction;
6. checks Apply kit, Corrections lists the corrections and deletes one, and the profile has the birth fields; then deletes the account.

The extension reaches the API through a small proxy in the run that records feedback and reports. If the API has no v2 routes (or `E2E_MOCK_V2=1`), the proxy answers them with 204, Corrections is served from what was recorded, and step 5 only records what was filled. `E2E_DRAFTING=0` turns drafting off so the run doesn't depend on the model.

## Known limits

- Cross-origin frames: `activeTab` covers the tab's own origin, so embedded forms from another origin are skipped.
- CAPTCHA, fully custom widgets that ignore input events, and ARIA-only choice widgets (left for the member).
- One question per screen flows (Typeform style) and multi-page forms: the panel notices each new step, but the member presses **Fill this step**.
- `activeTab` covers the tab where the toolbar button was pressed, and survives navigation within that site. After switching to another tab or another site, Chrome hides the page from the extension. Three ways back in, each granting that page: the toolbar button, the **Alt+Shift+F** shortcut (Fill this page with Blesser), or right-click → **Fill with Blesser**. The panel also offers **Allow on all sites**, an opt-in host permission that removes the per-page step; members can revoke it in Chrome's extension settings.
- `externally_connectable` origins are set at build time.
- Drafting waits on the model; the extension gives up after 75 seconds with a message suggesting drafting off.
- Firefox is Phase 5.

## Store submission checklist

- [ ] Release build with production `BLESSER_API_URL` and `BLESSER_APP_URL`; no `BLESSER_E2E_HOSTS`; check `dist/manifest.json` has no `host_permissions`.
- [ ] Bump `version` in `extension/package.json`; zip the contents of `extension/dist`.
- [ ] API `CORS_ORIGINS` includes `chrome-extension://<store id>` (and the Edge id).
- [ ] Privacy policy URL covering the Apply kit and the extension (the site's privacy page section from the plan).
- [ ] Permission justifications: `activeTab` (read and fill the form the member asked to fill), `scripting` (inject the filler on demand), `storage` (sign-in tokens and settings), `sidePanel` (the review panel that stays open beside the form), `contextMenus` (right-click Fill with Blesser, which grants the page like the toolbar button), optional host access (only if the member chooses Allow on all sites).
- [ ] Data disclosure: personal info, documents and form field descriptions are sent to Blesser to produce answers; corrections the member saves are stored for that member only; problem reports carry field descriptions and a note, never values; not sold, not used for ads, not shared beyond the configured model for drafting.
- [ ] Single purpose statement: fill application forms from the member's Blesser Apply kit.
- [ ] Screenshots (1280x800) of the side panel review list beside a filled form; 128 px icon (`public/icons/128.png`); store name (working: "Blesser: Apply with your kit").
- [ ] Edge Add-ons: same zip, separate listing; add the Edge extension id to CORS.
- [ ] Test the store build against production: connect, fill, Mark as applied, disconnect from Settings.

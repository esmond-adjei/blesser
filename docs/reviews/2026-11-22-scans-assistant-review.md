# Review: Scans and Assistant work since the last push

Scope: the 30 commits after `6398393` (the last pushed commit), about 1,900 added lines across `api/` and `webapp/`. Areas covered: scan rerun and steer, listing types, the scan canvas and composer, the crawler region filter and logging, owner access to unreviewed finds, the scan allowance card, Assistant bulk tools, the Continue button, the docked chat list, and paste-to-add sources.

Each finding gives the location, what goes wrong, a concrete way to see it, and a suggested fix. Severity:

- **High**: wrong results, lost data, a crash, or a safety net that no longer works.
- **Medium**: wrong in some cases, or a noticeable cost.
- **Low**: polish, small UX gaps, minor waste.

Items marked *confirmed* were reproduced during the review. The rest come from reading the code.

---

## Summary

| # | Severity | Area | Finding |
|---|----------|------|---------|
| 1 | High | Crawler | Region pre-filter permanently skips listings that are open to the scan's region *(confirmed)* |
| 2 | High | Logging | App logs no longer reach the root logger, so the CV privacy test can't fail *(confirmed)* |
| 3 | High | Scans API | Rerun with `"region": null` or `"focus": null` crashes with a 500 *(confirmed)* |
| 4 | High | Allowance | Steering a scan never uses up the allowance, so follow-up runs are unlimited |
| 5 | Medium | Performance | Every page polls the full scan list, which loads every task's log (about 55 kB each) |
| 6 | Medium | Web | Scan cards in chats poll every 5 seconds forever once the scan is deleted |
| 7 | Medium | Assistant | Bulk source proposals ignore the 10-source limit, so approved items then fail |
| 8 | Medium | Scans API | Two quick steers can both pass the "is it running" check and queue double work |
| 9 | Medium | Assistant | Continue appears whenever the turn used all 8 approval cards, even when nothing is left to do |
| 10 | Medium | Web | Paste sources clears the text after a partial failure, so failed sites can't be retried |
| 11 | Medium | Design | A "run" is guessed from tasks created within 5 seconds, in two places |
| 12 | Low | Scans | Rerunning an old scan that had several audiences silently keeps only the first |
| 13 | Low | Scans | Run again spends a scan with one click and no confirmation |
| 14 | Low | Web | The canvas layout effect runs on every pan movement |
| 15 | Low | Web | Several small accessibility gaps (tabs, fixed ids) |
| 16 | Low | Scans | Listing-type inference from the focus text gives odd titles |
| 17 | Low | Visibility | Two "which finds count" rules no longer agree |
| U1-U5 | Cleanup | Unused code | Catalogue-match tool, the "From the Blesser catalog" UI, an always-false subquery, and more |
| D1-D3 | Cleanup | Duplication | Allowance counting, listing-type words, and URL keys are each written twice |

---

## High

### 1. Region pre-filter permanently skips listings that are open to the scan's region *(confirmed)*

**Where:** `api/api/opportunities/triage.py:179` (`names_other_country`), used in `api/api/opportunities/pipeline.py` inside `run_pipeline`.

**What happens:** before fetching a crawler candidate, the pipeline checks the URL and title for country names. If they name only countries outside the scan's region, the candidate is marked `status="new"`, `reason="region_excluded:<region>"`. `claim_candidate` then skips candidates with that exact reason for that region, so they are **never retried for that region**.

The word list is too broad. It treats where a programme is *hosted*, or a partner's country, as who may *apply*. In the review, all of these returned `True` (skipped) for a Ghana scan:

```
https://x.org/lse-african-leadership-initiative-london-2027     -> london = UK
https://x.org/echoing-green-fellowship-new-york-global          -> new york = US
https://x.org/africa-accelerator-hosted-in-egypt-2027           -> egypt
https://x.org/india-africa-startup-fund                         -> india
```

Each of these could be open to Ghanaians. Once skipped, they are gone for every Ghana scan, and nothing records that the decision was a guess.

**Fix:**
1. **Narrow the rule.** Only skip when the text names a country *as the eligible group*: demonyms such as "nigerian graduates", "for young South Africans", "kenyan students", or phrases such as "in Nigeria only". Bare place names (London, New York, Egypt, India) should never skip on their own.
2. **Never skip when the text names Africa as a whole**: "africa", "african", "pan-african", "global", "international", "worldwide".
3. **Tag the guess:** use a different reason, e.g. `region_guess:<region>`, so these can be retried (for example after 7 days), or so the model extraction still gets a chance when nothing else is queued.
4. **Test the false positives:** add the four URLs above to `test_crawler_skips_links_that_name_only_other_countries` as must-not-skip cases.
5. **Recover what's already skipped:** run a one-off query to reset candidates the pre-filter skipped. They have `reason LIKE 'region_excluded:%'` and no `content_hash` (no page was ever fetched).

### 2. App logs no longer reach the root logger, so the CV privacy test can't fail *(confirmed)*

**Where:** `api/api/core/config.py:241` (`log_config_warnings`). Its new block adds a handler to the `api` logger and sets `propagate = False`.

**What happens:** after the app starts (lifespan) or the worker starts, every `api.*` log record stops at the `api` logger and never reaches the root logger. Three things break:

- **The privacy test is vacuous.** `tests/test_cv_import.py:317` (`test_model_failure_is_retryable_and_never_logs_the_cv`) uses `caplog`, which listens on the root logger. It now sees no `api.*` records, so it would pass even if CV text were logged. During the review, a record sent to `api.applicant_kit.cv` printed to the terminal but never reached a root handler.
- **Log collectors miss the app's logs.** Anything attached to the root logger in production (JSON logging, Sentry's logging integration, a log shipper) no longer receives them.
- **Hidden side effect.** The setup lives inside a function named for config warnings, so nobody would expect it to change logging.

**Fix:** keep propagation on and configure logging once, in its own function, called from `main.py` lifespan and `worker.py`:

```python
def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:  # leave alone when uvicorn --log-config or tests set it up
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
    logging.getLogger("api").setLevel(logging.INFO)
```

Then strengthen the CV test so it would fail if logging were cut off. For example, assert that some known non-sensitive `api.*` record *was* captured.

### 3. Rerun with `"region": null` or `"focus": null` crashes with a 500 *(confirmed)*

**Where:** `api/api/scans/routes.py:187` (`rerun_scan`) and `api/api/scans/service.py:127-129` (`start_scan`).

**What happens:** `ScanRerun` allows `region: str | None` and `focus: str | None`. With `exclude_unset=True`, an explicit `null` stays in `fields`, so `start_scan(region=None)` runs `None.strip()` and raises `AttributeError`. During the review, `ScanRerun.model_validate({"region": None, "focus": None}).model_dump(exclude_unset=True)` returned `{'region': None, 'focus': None}`.

The web app never sends `null`, but any other client (or a future form that clears a field) gets a 500. The scan-limit check has already run by then. It doesn't consume anything, but the request fails late.

**Fix:** treat `null` as "clear". Use `fields.get("region") or ""` and `fields.get("focus") or ""`, or make both fields plain `str` with no `None`. Add a test that posts `{"region": null}` and expects 201 with the default region.

### 4. Steering a scan never uses up the allowance, so follow-up runs are unlimited

**Where:** `api/api/scans/service.py:166` (`steer_scan`), `api/api/core/ratelimit.py:135` (`check_scan_limit`).

**What happens:** the steer route has `enforce_scan_limit`, but that only *checks* the count. The allowance counts `Scan` rows of kind `member` created in the last hour or day. A steer adds `ScanTask` rows to an existing scan and creates no `Scan`, so it is never counted. While a member has at least one scan left, they can steer any finished scan again and again. Each steer is a full agent run (about 5 minutes of model calls, about 65k input tokens in the run reviewed).

**Fix (pick one):**
- **Count steers:** store a `ScanRun` row, or a `steer_runs` timestamp list, and include those in both `check_scan_limit` and `scan_allowance` (see D1).
- **Simpler:** make a steer create a new `Scan` linked to the original (`parent_id`) rather than adding tasks. That also fixes item 11 and makes timing, finds and allowance straightforward.

Add a test: with the hourly limit at 1 and one scan used, a steer should be refused or counted.

---

## Medium

### 5. Every page polls the full scan list, which loads every task's log

**Where:**
- **Sidebar dot:** `webapp/src/components/layout/Shell.tsx:117` (`useScanning`) runs on every page and polls `GET /api/app/scans` every 60 seconds, or every 10 seconds while a scan runs.
- **Scan list:** `api/api/scans/service.py:362-382` (`list_scans`) loads full `ScanTask` rows for up to 50 scans.

**Cost:** a full row includes `log` (the JSON activity log) and `messages_json`. Locally, 16 tasks held 874 kB of those columns, about 55 kB per task. With 50 scans and 1 to 3 tasks each, one poll reads several MB from Postgres and parses it, only to compute `aggregate_metrics` and timing. The sidebar does this on every screen, including ones unrelated to scans.

**Fix:**
- **Load only what's needed:** in `list_scans`, select the columns metrics and timing use (`scan_id, status, created_at, started_at, finished_at, metrics, turns, input_tokens, output_tokens`), or put `log` and `messages_json` behind `deferred()` on the model so only the detail view loads them.
- **Cheap endpoint for the dot:** add something like `GET /api/app/scans/active` → `{"running": n}` and use it in `useScanning`. Keep the `["scans"]` key for the Scans page only.

### 6. Scan cards in chats poll every 5 seconds forever once the scan is deleted

**Where:** `webapp/src/components/assistant/RecordCards.tsx:76`.

**What happens:** `refetchInterval: ({ state: { data } }) => (data && data.status !== "running" ? false : 5000)`. If the request fails (the scan was deleted, so 404), `data` stays `undefined` and the card asks the server again every 5 seconds for as long as the chat is open. Each scan card in an old chat also fetches the full scan detail, logs included, when the chat opens.

**Fix:** stop on error, and only poll while running:

```ts
refetchInterval: ({ state }) => (state.status === "error" || state.data?.status !== "running" ? false : 5000),
```

Consider a lighter status endpoint, or reusing the `["scans"]` list data when it's already cached.

### 7. Bulk source proposals ignore the 10-source limit

**Where:** `api/api/assistant/toolkit/scans.py` (`propose_add_source`, and `propose_add_sources` built from `bulk` in `toolkit/base.py:144`).

**What happens:** proposals don't check the member's source count; only `sources.add_source` does, at apply time. A member with 8 sources can approve "Add 4 sources". The first 2 are added, the other 2 fail with "You can save up to 10 sources", and the member learns this only after approving. The approval card promised 4. Duplicate URLs in one list behave the same way (the second fails at apply).

**Fix:**
- **Check up front:** give `propose_add_source` an optional `taken` count. In the bulk `propose`, count the member's sources once, then refuse (or trim, with a note on the card) when `existing + len(items)` is over the limit.
- **Dedupe:** use `normalized_url` on the items before building the proposal.
- **Generalise:** a `bulk(..., limit=...)` hook could cover answers and to-dos too, if those ever get limits.

### 8. Two quick steers can both pass the "is it running" check

**Where:** `api/api/scans/service.py:166` (`steer_scan`).

**What happens:** it reads `scan.status`, adds tasks, then sets `status="running"`, with no lock. Two steer requests at nearly the same moment (a double-tap, or two tabs) both see `done` and both queue a full set of tasks. That is twice the agent cost, and with item 4 neither is counted.

**Fix:** lock the row with `select(...).with_for_update()` on the scan, or use the advisory-lock pattern from `check_scan_limit` (`pg_advisory_xact_lock(hashtext('scan-steer:'+scan_id))`), then re-check the status.

### 9. Continue appears whenever the turn used all 8 approval cards

**Where:** `api/api/assistant/service.py:424`. It sets `stopped = step > MAX_STEPS or not changes_allowed`, which is then saved as `can_continue`.

**What happens:** `not changes_allowed` is true whenever `turn.cards >= MAX_CARDS` (8). A turn where the member approved 8 changes and the model then finishes normally still gets the Continue button, even though nothing is left to do. The step-limit half is right: the model was forced to answer without tools.

**Fix:** only flag the card limit when it actually blocked something: the model asked for a change tool after the limit was reached (that call currently returns `tool_unavailable`). Track that as `turn.blocked = True` where the unavailable-tool result is produced, and use `stopped = step > MAX_STEPS or turn.blocked`.

### 10. Paste sources clears the text after a partial failure

**Where:** `webapp/src/components/scans/PasteSources.tsx:41`.

**What happens:** `onSuccess` always runs `setText("")` and `setEdits({})`, even when some sites failed. The failures are named in a toast, but the parsed rows and the member's edits to them (audience, note) are gone, so retrying means pasting again.

**Fix:** on partial failure, keep the text and mark the added rows. Because `existing` refreshes after `onAdded()`, simply *not* clearing the text leaves only the failed rows showing, since the added ones drop out as "already in your sources". Clear only when `failed.length === 0`.

### 11. A "run" is guessed from tasks created within 5 seconds, in two places

**Where:** `api/api/scans/service.py:320-327` (`RUN_WINDOW`, `latest_run`) and `webapp/src/lib/scanLog.ts:111` (5000 ms).

**What happens:** "Running for…" and "Finished in…" are measured from the latest run, defined as tasks created within 5 seconds of the newest task. This works today only because a scan's tasks and a steer's tasks are each inserted in one transaction. It breaks if:
- a slow multi-audience scan inserts tasks more than 5 seconds apart,
- a steer happens within 5 seconds of the scan's tasks being created, or
- the two copies drift apart.

**Fix:** record the run explicitly. Either add a `run` integer (or `run_id`) to `ScanTask`, set when tasks are queued (0 for the first run, +1 per steer), or adopt the "steer creates a child `Scan`" approach from item 4. Then `latest_run` becomes `max(run)` and the web app reads `scan.started_at` / `finished_at` from the API rather than recomputing.

---

## Low

### 12. Rerunning an old multi-audience scan keeps only the first audience

**Where:** `webapp/src/pages/Scans.tsx`, `ScanComposer` with `from`: `category` is initialised to `from.categories[0]`.

Older scans can have several categories (cards titled "Startups, Researchers…"). "Edit and run again" sends `categories: [first]`, dropping the rest without saying so. Plain "Run again" keeps them, because the API falls back to `original.categories`.

**Fix:** if `from.categories.length > 1`, show a one-line note in the edit dialog ("This scan covered 3 audiences. Running it again keeps one."). Alternatively, only send `categories` when the member changed the picker.

### 13. Run again spends a scan with one click and no confirmation

**Where:** `webapp/src/pages/Scans.tsx:696` (`useRerunActions`).

The menu item fires the mutation immediately. Starting a scan from the composer is deliberate, but a menu item sits near "Open scan" and "Repeat weekly". The allowance is small (3 an hour).

**Fix:** show the scans left in the menu item's label ("Run again, 2 left this hour"), or ask for a short confirmation when 1 or fewer scans are left.

### 14. The canvas layout effect runs on every pan movement

**Where:** `webapp/src/pages/Scans.tsx:197-218`.

The effect depends on `offset.y`. During a pan, `setOffset` runs on every pointer move, and each move rebuilds `Object.entries(layout)`, a `Set` of ids, and a filtered copy before returning early. That's cheap with 13 cards, but wasteful, and it sets state inside an effect.

**Fix:** read the offset through a ref (`offsetRef.current`) inside the effect and drop `offset.y` from the dependencies. Do the "pan to new card" step only when `missing.length > 0`.

### 15. Small accessibility gaps

- **Tabs:** `webapp/src/components/scans/SourcesDialog.tsx:70` uses `role="tab"` buttons with no `role="tabpanel"`, no `aria-controls`, and no arrow-key handling. Either make them a real tab pattern, or use a segmented control (`role="radiogroup"` with `role="radio"`, like the audience switch).
- **Fixed id:** `webapp/src/components/scans/PasteSources.tsx:53` uses `id="paste-sources"`. Use `useId()` as the composer now does.
- **Listbox semantics:** `TargetSelect` puts real `<button>`s inside `role="option"` items, which makes for nested interactive semantics. Use `role="menuitemcheckbox"` inside a `role="menu"`, or plain buttons with `aria-pressed` and no listbox roles.

### 16. Listing-type inference from the focus text gives odd titles

**Where:** `api/api/scans/service.py:76` (`_KIND_WORDS`) and `webapp/src/lib/scanKinds.ts:35`.

These loose substring matches drive card titles for scans that have no picked types:

| Matched word | Inferred type | Example that misfires |
|---|---|---|
| "course" | training | "of course" |
| "career" | job | "careers page" |
| "challenge" | competition | "challenges facing founders" |
| "funding" | grant | "funding rounds" |
| "proposals" | call for proposals | any mention of proposals |

It only affects titles, not what the agent does, but the titles can mislead.

**Fix:** use word-boundary matches, and stop inferring once real `kinds` exist, which is the case for every new scan. Once old scans age out, consider dropping inference altogether (see D2).

### 17. Two "which finds count" rules no longer agree

**Where:** `api/api/scans/service.py:266` (`_visible_find`) versus `api/api/scans/schedules.py:104` (`_visible`).

`_visible_find` now means "created by this scan, and published, in review or draft". `schedules._visible` still means "any published find, or a created one in review or draft", so it counts catalogue re-saves for weekly runs. Its `run_counts` only reports `created` and `updated` counts, so the numbers happen to come out right, but the two rules will drift.

**Fix:** have `schedules.py` import and use `service._visible_find()` (rename it to `visible_find`), or document why weekly counts need the wider rule.

---

## Unused code (safe to remove)

### U1. The `add_catalogue_match` agent tool

Member scans stopped offering it (`opportunities/tasks.py`, `tools += ["search_catalogue"]`), and finds that weren't created by the scan are no longer shown. What remains:

- `api/api/agent/tools/definitions.py:163`: the tool definition.
- `api/api/agent/tools/dispatch.py:31-33`: the "record it with add_catalogue_match" hint, which can never trigger now.
- `api/api/agent/tools/dispatch.py:98`: the dispatch entry.
- `api/api/agent/orchestrator.py:308`: the `add_catalogue_match ... result.get("added")` branch.
- `api/api/opportunities/tools.py:383`: `handle_add_catalogue_match` and `ctx.catalogue_matches`.
- `api/tests/test_member_scans.py:174`: `test_catalogue_matches_only_open_published_listings`.
- `ScanFind.via == "catalog"` rows: no longer written. Existing rows can stay; they're filtered out.

### U2. "From the Blesser catalog" in scan results

`_visible_find` now requires `created`, so every find is from the web. Remove:

- **API:** `api/api/scans/service.py:447`. `"source": "web" if created else "catalog"` is always `"web"`, and `source_domain if created` is always set.
- **Web, find row:** `webapp/src/pages/Scans.tsx:1104` (the `"From the Blesser catalog"` branch).
- **Web, header:** `webapp/src/pages/Scans.tsx:1055`. ", N new to Blesser" always equals the total, so it repeats the count, which the copy rules forbid.
- **Types:** `webapp/src/lib/types.ts:108`. The `source: "catalog"` union member.

### U3. The "seen in an earlier scan" subquery

`api/api/scans/service.py` (`_scan_finds`, the `seen` EXISTS). It checks whether an earlier scan by the same member found the same listing. A *created* find is the first time that listing existed, so the answer is always false and `is_new` is always true. It's a correlated subquery that runs per row and does nothing. Remove it and `is_new`, or keep `is_new` as a constant until the web stops reading it.

### U4. The `ScanFind.source_url` column (verify first)

It's only written when `created`, and only read for created finds. That's fine as is. It's listed here to note that the `created` condition is now always true on the read path, so `found_url if created else opportunity.source_url` can be simplified.

### U5. A formatter leftover

`webapp/src/components/scans/PasteSources.tsx`, the `<Input ... />` props: a stray blank line before `/>`. Cosmetic.

---

## Duplication

### D1. Allowance counting is written twice

`api/api/core/ratelimit.py:135` (`check_scan_limit`) and `api/api/scans/service.py:523` (`scan_allowance`) both count `Scan` rows of kind `member` over the hour and the day. If one changes, for example to count steers (item 4), the card and the enforcement will disagree. **Fix:** one helper, e.g. `scans.service.allowance_usage(session, user_id) -> {window: [created_at...]}`, used by both.

### D2. Listing-type words and plurals are written twice

`api/api/scans/service.py:62-100` (`KIND_PLURALS`, `_KIND_WORDS`, `scan_kinds`, `kinds_phrase`) is mirrored in `webapp/src/lib/scanKinds.ts`. **Fix:** have the API return a `title` (or `what`) string on `ScanOut`, and drop the TypeScript copy. The Assistant already uses the Python version.

### D3. URL keys are normalised three ways

- `webapp/src/lib/parseSources.ts`: `key`.
- `webapp/src/components/scans/PasteSources.tsx`: `key`, a separate copy.
- The API's `normalized_url`.

They can disagree (query strings, trailing paths), so a pasted site can look new in the web app and then be rejected as a duplicate. **Fix:** export one `sourceKey` from `parseSources.ts` and use it in `PasteSources`. Accept that the server is the final judge, and show its "already in your sources" error for that row.

---

## Failing test

The full API suite: 939 passed, 1 failed.

`tests/test_architecture.py::test_member_catalogue_new_filters_and_aliases` (line 368) checks the exact field set of a member listing against `MEMBER_FIELDS`. Commit `bcd74a5` added `in_review` to `to_out` and `MemberOpportunity`, so the set no longer matches. **Fix:** add `"in_review"` to `MEMBER_FIELDS` in that test. The field is `False` for anyone but the owner, so nothing private is exposed.

## Test gaps

- **Item 2:** the CV logging test needs a positive check so it can't pass vacuously.
- **Item 3:** no test posts `null` fields to `/rerun`.
- **Item 4:** no test that a steer counts toward the allowance.
- **Item 1:** the region filter tests have no "must not skip" cases (London, New York, Egypt, India-Africa).
- **Item 7:** bulk tests don't cover "proposal larger than the space left".
- **Web:** no render tests for `TargetSelect`, `SteerBar`, `PasteSources`, or the canvas placement logic. `freeSlot` and the prune-and-pan step could be pulled into a pure function and unit-tested.

---

## Suggested order

1. **Items 2 and 3.** Small, contained, and they restore a safety net and remove a crash.
2. **Item 1.** Narrow the filter, then reset what it wrongly skipped.
3. **Items 4, 8 and 11 together.** Decide how a steer is stored: a child scan, or a run number. All three follow from that.
4. **Items 5 and 6.** Load less and poll less.
5. **Items 7, 9 and 10.** Assistant and paste UX correctness.
6. **Cleanup U1 to U5 and D1 to D3**, then the Low items.

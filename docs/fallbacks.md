# External tools: fallbacks and honest degradation

Every flow-critical external call has an ordered alternative, or a
documented way it fails. The effective order is visible in Settings →
Agents & tools → *External services & fallbacks* (`GET /api/agent/fallbacks`).

| Capability | Used by | Order tried | When all fail |
|---|---|---|---|
| Web search | discovery, chat | `SEARCH_PROVIDERS` (e.g. `tavily,brave`; unkeyed ones are skipped; `duckduckgo` is opt-in) → recent cached results for the same query (`SEARCH_CACHE_SECONDS`, default 6 h, marked `stale`) | the tool returns "search is unavailable (tried: …)" and the agent works from known URLs |
| Read a page | discovery, research, chat | direct → `FETCH_FALLBACKS` (`archive` = Internet Archive's latest snapshot, prefixed with an out-of-date notice) | guidance text, never an exception |
| Publication records | research, chat | ORCID / DBLP ids linked on the faculty page → OpenAlex (with `OPENALEX_API_KEY`), bounded retries on 5xx/transport errors and short 429s (honouring `Retry-After`) → DBLP (computing fields) → NIH RePORTER → NSF awards (US schools), see [verification-sources.md](verification-sources.md); research tasks only, chat uses OpenAlex alone | the agent is told not to invent papers and to say publications couldn't be checked; when the daily budget is used up and no other source verifies the professor, professor tasks wait for the reset instead (below) |
| Fit scoring | research, chat | `EMBEDDING_PROVIDER` → local TF-IDF | (always succeeds) |
| Model | every flow | the run's or chat's pick, else Auto (the system model; your default own model if you turned on "Use my model by default") | turns fail visibly; chat retries (#10), tasks re-run |

Every search result carries `source` (`tavily`, `brave`, `duckduckgo`,
`cache:<provider>`), so traces show who answered.

OpenAlex prices usage per request. Without `OPENALEX_API_KEY`, every
caller on the server's IP shares a free budget of about $0.10 a day
(roughly 100 author searches), after which every lookup is a 429 until
midnight UTC. A free key (`POST https://api.openalex.org/api-keys` with
`{"email": ...}`, then confirm the email) has its own budget of about
$1 a day; prepaid credit costs cents per run. When the budget runs out
anyway (a 429 asking to wait more than 30 s, or `X-RateLimit-Remaining-USD`
reaching 0), the worker stops calling OpenAlex until the reset, and
professor tasks that need it go back to the queue marked "Waiting for
OpenAlex" instead of spending model tokens on saves that can't be
verified (a code-first task first tries DBLP and the grant databases,
and only waits when none of them verifies the professor). They resume
spread over `OPENALEX_RESUME_SPREAD_SECONDS`
(default 10 minutes) after the reset. Within a task, a lookup that
already failed is answered from memory instead of being sent again.

A 401 or 403 means OpenAlex rejected the key (wrong, revoked or
unfunded). That is a server-wide misconfiguration, not a failed lookup:
the worker logs one ERROR ("OpenAlex rejected the API key ... Check
OPENALEX_API_KEY"), stops calling OpenAlex, and professor tasks wait the
same way, marked "Waiting for OpenAlex: the server's API key was
rejected". The key is tried again every `OPENALEX_AUTH_RECHECK_SECONDS`
(default 5 minutes), so fixing it needs no restart. Topic ranking,
institution lookups and Gradis chat treat it as an outage and carry on.

OpenAlex bills a name search ten times a list call. A professor is
first looked up in their school's author list (`/authors` filtered by the
school's institution, most published first, `OPENALEX_ROSTER_PAGES` pages
of 200), matched on first and last names in any order; only a name not on
the list is searched. Responses are kept in Postgres (`openalex_responses`,
`OPENALEX_DB_CACHE_DAYS`, 30 days for school lists and institutions), so
the API and every worker share them and a repeat school costs nothing.

Keys: `TAVILY_API_KEY`, `BRAVE_API_KEY` (the legacy `SEARCH_API_KEY`
still serves `SEARCH_PROVIDER`). DuckDuckGo needs no key but scrapes an
HTML endpoint its terms likely forbid, so it only runs when listed in
`SEARCH_PROVIDERS` explicitly; with no search key configured, discovery
works from URLs the agent already knows.

User-defined flows (#32) inherit these chains: a flow picks capabilities
(tool groups), and the server-side chain behind each one applies.

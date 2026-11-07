# Verifying professors beyond OpenAlex

OpenAlex used to be the only source both for verifying a professor (the
right person, at this school) and for the works behind the alignment
score. The score only needs titles and abstracts, so research tasks now
also use free sources whose terms allow commercial use (#173). Code:
`api/prospects/sources.py` (the chain), `profile_ids.py`, `dblp.py`,
`grants.py`, `source_http.py`.

## Order

| Step | Source | When | What it gives |
|---|---|---|---|
| 1 | Faculty-page ids | always, before OpenAlex | an ORCID iD or DBLP id linked next to the professor's name on the school's pages already read; the school's own link is identity proof, so no institution match is needed |
| 2 | OpenAlex | as before | author, works with abstracts |
| 3 | DBLP | OpenAlex has nobody at the school, or is unavailable (including its budget breaker); computing fields only | author with that name whose DBLP affiliation is the school; recent publication titles |
| 4 | NIH RePORTER, then NSF awards | same; US (or unknown-country) schools only | principal investigator with that name at the school; award titles and abstracts |
| 5 | ORCID | same; every field and country (#227) | a record with that name whose institutions include the school; recent work titles, years, journals and DOIs |
| + | Semantic Scholar | after DBLP or ORCID found someone | abstracts, by DOI, for the works they listed (many abstracts are withheld by publishers, so coverage is partial) |

- An ORCID iD from the faculty page is resolved with OpenAlex's author
  filter (`/authors?filter=orcid:...`, a list call, not a search). While
  OpenAlex is waiting out its budget or key, the iD is read from ORCID
  itself instead (the school's link is still the identity proof). A DBLP
  id is resolved through DBLP. Google
  Scholar and Semantic Scholar links are read off the page and kept as the
  professor's links, but those services are never contacted.
- Ids are read only from pages `fetch_page` already downloaded. A link
  belongs to the names in the largest part of the page holding no second
  id of one kind (a directory card), or, when that part is the whole
  page, to the person its title or main heading names. The name the id
  resolves to must still match.
- "Computing field": the run's field or the programme's name mentions
  computing, software, AI, machine learning, robotics, data science, and
  similar.
- ORCID's own institution filter is a loose text match, so people are
  searched by name and their record's institutions are matched here.
- Institution matching for DBLP, ORCID and the grant databases has no
  institution id to compare, so it is strict: the school's name (or its
  acronym, or an OpenAlex alternative name) must appear in order in the
  affiliation. "University of Washington" does not match "Washington
  University in St. Louis".

## How it is grounded and stored

Candidates from another source carry a prefixed id (`dblp:<pid>`,
`nih:<profile id>`, `nsf:<name>@<awardee>`, `orcid:<iD>`) and a `source`, and their works
are recorded with the lookup, so `score_alignment` and
`save_professor_record` take that id like an OpenAlex id and ground the
save the same way. Such a professor is stored without an OpenAlex id; the
source's profile (DBLP page, RePORTER project, NSF award) is added to
their links, and the rationale ends with where the verification came from:

- DBLP and ORCID: "scored on publication titles only, so lower confidence",
  or, when Semantic Scholar supplied some, "scored on N abstracts and M
  titles";
- NIH / NSF: "scored on grant abstracts, not papers" (grants are stored
  as papers, with `[NIH grant R01...]` / `[NSF award ...]` after the title
  and a link to the award).

For a likely match, awards still running for a PI with that name at the
school go into the save brief as a funding signal, and the rationale
mentions one when it is on the student's topic.

A code-first task whose OpenAlex is waiting out its budget is not parked
up front any more: it tries DBLP, the grant databases and ORCID, and waits
for OpenAlex only when none of them verifies the professor. Other tasks
(discovery, faculty lists, email drafts) never wait for OpenAlex.

## Terms, limits and failures

| Source | Terms | Politeness here |
|---|---|---|
| DBLP | data under CC0 1.0 | 1 request/s; DBLP answers bursts with 429 + `Retry-After` |
| NIH RePORTER API | public US government data, no key | 1 request/s (NIH's guidance) |
| NSF Awards API | public US government data, no key | 1 request/s |
| ORCID public API | public records under CC0, no key | 2 requests/s (well under ORCID's anonymous limit) |
| Semantic Scholar Graph API | free; `SEMANTIC_SCHOLAR_API_KEY` optional | one batch call per professor, about 1 request/s keyless |

Every request has a `SOURCE_TIMEOUT_SECONDS` timeout. A failure (timeout,
5xx, 429) skips that source for `SOURCE_OUTAGE_SECONDS` (or the server's
`Retry-After`), and a request that would wait longer than
`SOURCE_MAX_QUEUE_SECONDS` for its slot is skipped. A skipped or failed
source means "no answer from it": the chain moves on and the task never
fails because of it. Successful responses are kept in process
(`SOURCE_CACHE_SECONDS`) and in the Postgres response store
(`openalex_responses`, `OPENALEX_DB_CACHE_DAYS`) under a source prefix.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `VERIFICATION_SOURCES` | `faculty_page,dblp,nih,nsf,orcid,semantic_scholar` | sources in use; remove a name to switch it off (the order of DBLP, the grant databases and ORCID follows the list) |
| `SOURCE_TIMEOUT_SECONDS` | 10 | per request |
| `SOURCE_MIN_INTERVAL_SECONDS` | `{"dblp": 1.0, "nih": 1.0, "nsf": 1.0, "orcid": 0.5, "semantic_scholar": 1.1}` | least gap between two requests to a source, process-wide |
| `SEMANTIC_SCHOLAR_API_KEY` | empty | Semantic Scholar's own rate limit instead of the shared keyless one |
| `SOURCE_MAX_QUEUE_SECONDS` | 15 | longest wait for a slot before a request is skipped |
| `SOURCE_OUTAGE_SECONDS` | 300 | how long a failing source is skipped |
| `SOURCE_CACHE_SECONDS` | 86400 | in-process response cache |

Settings → Agents & tools → *External services & fallbacks* shows which
sources are on. Gradis chat still uses OpenAlex alone.

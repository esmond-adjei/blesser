# Changelog

## Unreleased

### Blesser

- A public opportunity catalogue for startups, researchers and students in Ghana: grants, accelerators, incubators, fellowships, scholarships, internships, competitions and calls for proposals. Browse without an account; filter by audience, kind, country, closing date and keyword.
- Discovery agents add opportunities with `save_opportunity`. A save must cite a page fetched in the same task, the page must name the opportunity, and a stated deadline must appear on it. Duplicates merge into one listing.
- Scans: start one, follow its activity log as it runs, stop or delete it. Optionally the worker runs a scan every N hours (`OPPORTUNITY_SWEEP_EMAIL`, `OPPORTUNITY_SWEEP_HOURS`).
- Applications: track an opportunity from saved to accepted, with a requirements checklist, notes and deadline reminders.
- To-dos linked to opportunities or applications, grouped by due date.
- Calendar sync: a Google Calendar link and an `.ics` file per opportunity, and a private, rotatable subscription feed of deadlines and dated to-dos.
- Community submissions, reviewed and published in the admin console by editors and admins.
- A public site (Astro) for the catalogue, and an admin console for review, editing, collections, sources, users and settings.
- The Assistant: ask about opportunities, applications and to-dos; it proposes tracking or a to-do and acts once the member confirms.
- The Apply kit (profile, projects, documents, saved answers) and a browser extension that fills application forms from it for review.
- Fill the Apply kit profile from a CV: pick one from Documents or upload a PDF or Word file, check what Blesser found, and add only the details you tick. Fields the CV lacks stay empty, existing values are never replaced unless you choose, and national ID and passport details are never read.
- Notifications: an in-app inbox with select and delete, browser push and email for deadline reminders and scan results, with quiet hours, a daily digest and per-kind settings.
- The web app builds on Node 26 LTS.
- The crawler reads the newest pages first: feed items by publish date, sitemaps by last-updated date, then sources that have produced saves. Duplicate URL checks use a stored, indexed normalized URL.
- The crawler reads PDF calls in a sandboxed parser with size, page, time and memory limits, and ten more Ghana sources are seeded: the Ghana Scholarships Authority, University of Ghana and KNUST notices, AREF, the Japan embassy and GREAT Scholarships (GEA and GETFund are seeded disabled).
- Listings stay current: the worker re-checks listing pages on a schedule (unchanged pages without a model, changed ones with an agent), sends lost pages to review, archives undated listings nothing has confirmed for 120 days, and reopens a closed listing when its page opens a new cycle.
- Fewer duplicates: the dedupe key ignores years, cycle words and words like "Foundation", organization aliases cover other names, and a Duplicates page in the admin console lists likely pairs to merge or dismiss. Merging moves tracking, to-dos, reports and links to the kept listing.
- Search uses Postgres full-text search: plurals and word stems match, a word still being typed matches as a prefix, and "Best match" ranks by match quality.
- "What you're looking for" in Settings: audiences, kinds, stage, fields and countries, suggested from the Apply kit. The For you order ranks listings by it and leaves out listings closed to the member's countries.
- Saved searches, and alerts for new listings that fit the member (daily or weekly), a weekly "closing soon that fit you" list, and new results for saved searches.
- Member scans follow the member's request: the agent matches existing catalogue listings first, then reads up to five sites the member names, then searches the web. A scan shows every listing that fits, matched or new, and its notification says how many were found and how many are new. Crawler saves no longer use the member's save limit, and finds from member sites wait for staff review.
- My sources: members save up to 10 sites they trust, and Blesser checks them every 7 days (or on demand, once an hour) with the scan agent, without web search. Checks don't use the scan quota, and finds wait for staff review.
- Listings point at the funder's own page, not an aggregator's repost. Crawler finds on aggregator sites are followed to the official page, which is checked and stored with its deadline; finds with no official page wait for staff review. The agent may not save aggregator pages. Staff edit the aggregator list in Settings, and a backfill (dry run first) moves existing listings.

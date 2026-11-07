# Changelog

## Unreleased

### Blesser (forked from Graduator at b6747b4)

- A public opportunity catalogue for startups, researchers and students in Ghana: grants, accelerators, incubators, fellowships, scholarships, internships, competitions and calls for proposals. Browse without an account; filter by audience, kind, country, closing date and keyword.
- Discovery agents add opportunities with `save_opportunity`. A save must cite a page fetched in the same task, the page must name the opportunity, and a stated deadline must appear on it. Duplicates merge into one listing.
- Scans: start one, watch each agent's steps, stop or delete it. Optionally the worker runs a scan every N hours (`OPPORTUNITY_SWEEP_EMAIL`, `OPPORTUNITY_SWEEP_HOURS`).
- Applications: track an opportunity from saved to accepted, with a requirements checklist, notes and deadline reminders.
- To-dos linked to opportunities or applications, grouped by due date.
- Calendar sync: a Google Calendar link and an `.ics` file per opportunity, and a private, rotatable subscription feed of deadlines and dated to-dos.
- Community submissions, published by ops admins.
- Everything specific to graduate-school research was removed: programme and professor research, scoring, outreach drafts, the CV editor, the Gradis chat assistant, billing and plans, per-account model and tool settings, flows, data export and the marketing site.
- One baseline migration replaces Graduator's 55. The web app builds on Node 26 LTS.

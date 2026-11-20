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
- Notifications: an in-app inbox with select and delete, browser push and email for deadline reminders and scan results, with quiet hours, a daily digest and per-kind settings.
- The web app builds on Node 26 LTS.
- Search uses Postgres full-text search: plurals and word stems match, a word still being typed matches as a prefix, and "Best match" ranks by match quality.
- "What you're looking for" in Settings: audiences, kinds, stage, fields and countries, suggested from the Apply kit. The For you order ranks listings by it and leaves out listings closed to the member's countries.
- Saved searches, and alerts for new listings that fit the member (daily or weekly), a weekly "closing soon that fit you" list, and new results for saved searches.

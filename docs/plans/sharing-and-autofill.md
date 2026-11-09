# Plan: sharing opportunities and autofilling applications

Two member features:

1. **Share an opportunity**: a branded image plus ready-to-post text for any social network.
2. **Apply with Blesser**: a browser extension that fills application forms from what a member keeps on Blesser (their profile, CV and other files, and projects such as "Siwa"), leaving them to review and submit.

Both build on the member app and the API. The extension needs a new foundation, the **applicant kit**: profile, projects, documents and saved answers.

## Phases

| Phase | Ships | Depends on |
|---|---|---|
| 1. Share | Share dialog, branded images, captions, share links, Open Graph images on public pages | nothing |
| 2. Applicant kit | Profile, projects, documents, answer library: API, storage and member-app screens | nothing (runs alongside 1) |
| 3. Autofill engine | `/api/app/autofill` field matching and drafting, extension tokens | 2 |
| 4. Extension | Chrome/Edge extension (MV3), connect flow, connected-apps settings | 3 |
| 5. Later | Firefox, "save this answer" learning, site-specific adapters, S3 storage | 4 |

---

## 1. Share an opportunity

### What the member sees

A **Share** action on every opportunity card, list row and detail view, in the member app and on public opportunity pages. It opens a dialog with:

- A live preview of the image, with a format switch: **Square** (1080x1080, Instagram, WhatsApp, Facebook), **Wide** (1200x630, LinkedIn, X, link previews) and **Story** (1080x1920).
- Caption variants with a Copy button each: **Short** (fits X's 280 characters with the link), **Standard** (LinkedIn, Facebook, WhatsApp), and **With hashtags**.
- **Download image**, **Copy link**, a native **Share…** button where the browser supports sharing files (most phones), and quick links for WhatsApp, X, LinkedIn, Facebook and email.

### The image

- Content: kind and category ("Grant · Startups"), the title, what's on offer (the `benefits` line, trimmed), "Offered by {organization}", the deadline ("Closes 21 Nov 2026" or "Rolling"), and the opportunity's generated art (`OpportunityArt`, same seed as its card).
- Brand: a footer band reading **"Found on Blesser"** with the Path mark and the short link. This marks the source of the find, not the offer.
- **No implied endorsement**: no funder logos, never "Blesser presents" or "in partnership with". The organization appears only as text after "Offered by".
- Rendered by the **public site's Node server** with Satori (JSX to SVG) and resvg (SVG to PNG). The image reuses `OpportunityArt` and the brand fonts (TTF/WOFF files). Responses are cached (`Cache-Control: public, max-age=86400`, and the ETag changes when the opportunity changes).
- The Wide image doubles as the `og:image` of public opportunity pages, so pasted links unfurl well.

### Share links and members-only opportunities

- `POST /api/app/opportunities/{id}/share` returns everything the dialog needs (below). The share link is `{SITE_URL}/s/{token}`. The token is a stateless HMAC-signed `(opportunity_id, sharer_id)` using `AUTH_SECRET`-derived key, base64url, so we can count referrals later without a table.
- `/s/{token}` on the site:
  - **Public** opportunity: 302 redirect to `/opportunities/{slug}?ref=share`.
  - **Members-only** opportunity: a teaser page with the same image, title, organization, offer and deadline, and a "Create a free account to see the details and apply" call to action that leads to `register?track={slug}`. The official link stays behind sign-in. A member chose to share it, so this is the only route that exposes a members-only teaser.
  - **Hidden, draft, invalid token**: 404. **Archived**: the closed page.
- Public pages also get a Share button (public opportunities only) that uses the same images and captions with no sharer in the link.

### Caption templates (deterministic, no model)

Built by the API from the opportunity's own fields. Standard:

```
{title}
Offered by {organization}

{benefits}
{eligibility, first sentence, if short}
Deadline: {21 Nov 2026 | Rolling, apply any time}

Details and the official link: {share_url}
Spotted on Blesser, where we gather open opportunities for people in Ghana. Blesser is not affiliated with {organization}; always apply on the official page.
```

Short: `{title} ({organization}). {benefits, trimmed}. Deadline {date}. {share_url} via Blesser`, guaranteed ≤ 280 characters by trimming the benefit first, then the title. Hashtags: derived from category and kind (`#Grants #Startups #Ghana`), at most four.

### API (additions)

```ts
// POST /api/app/opportunities/{id}/share   (member; any opportunity the member can see)
// GET  /api/public/opportunities/{slug}/share  (public opportunities only; no sharer)
type ShareKit = {
  share_url: string;
  images: { square: string; wide: string; story: string };   // absolute URLs on the site
  captions: { short: string; standard: string; hashtags: string };
  disclaimer: string;   // "Blesser is not affiliated with {organization}."
}
// GET /api/public/shared/{token} -> SharedTeaser | 404   (used by the site's /s/{token} and image routes)
type SharedTeaser = { slug: string; audience: "public" | "members"; status: "published" | "archived";
  title: string; organization: string; category: string; kind: string; benefits: string;
  deadline: string; deadline_date: string | null; rolling: boolean; seed: string }
```

Site routes: `/s/{token}`, `/share/{token}/{square|wide|story}.png`, `/opportunities/{slug}/og.png`.

---

## 2. Applicant kit

What a member keeps on Blesser so forms can be filled from it. One **profile** per member, any number of **projects**, a **document** library, and an **answer library**.

### Profile (one per member)

- Identity: given name, family name, preferred name, pronouns (optional), date of birth, gender (optional), nationality, country of residence, city, address lines, postal code.
- Contact: email (defaults to the account email), phone, LinkedIn, website, GitHub, other links.
- About: headline (one line), short bio (≤ 300 characters), long bio.
- Education: list of { institution, qualification, field, start, end, grade, country }.
- Experience: list of { organization, role, start, end or current, location, summary }.
- Skills, languages (with level), awards, publications (title, venue, year, link).
- References: list of { name, title, organization, email, phone, relationship }.
- Sensitive: national ID number, passport number and expiry. Encrypted at rest with a Fernet key from `SECRETS_KEY`, never sent to a model, filled only into fields detected as those exact fields.

### Projects (many per member)

For ventures, research projects or community work, e.g. "Siwa".

- Basics: name, tagline, website, logo (a document), stage (idea, prototype, early revenue, growth), sector, country, city, founded on, legal status, registration number.
- Story: problem, solution, target customers, market size, business model, competition and advantage, traction, impact (with metrics), why now.
- Team: list of { name, role, bio, email, linkedin, is_founder, gender (optional, for funds that ask) }, team size, women-led / youth-led flags.
- Money: revenue last 12 months, funding raised so far, amount sought, currency, use of funds.
- Documents: links to pitch deck, financials, budget, registration certificate, etc. in the library.
- Custom fields: label/value pairs for anything the form asks that the schema does not cover.

### Documents

- Upload CVs, cover letters, pitch decks, transcripts, certificates, budgets, IDs, photos and logos. Each has a `kind` tag (`cv`, `cover_letter`, `pitch_deck`, `transcript`, `certificate`, `budget`, `financials`, `id_document`, `photo`, `logo`, `other`), a title, and optional links to the profile or projects. One document per kind can be the default.
- Limits: 15 MB per file; types pdf, doc, docx, ppt, pptx, xls, xlsx, csv, png, jpg, webp; 250 MB per member. Content type checked by magic bytes, not the extension.
- Storage behind a small interface: local disk under `UPLOAD_DIR` (a Docker volume) now, S3-compatible later. Files are private: served only to their owner through an authenticated download route, with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.

### Answer library

Reusable answers to common questions ("Describe your solution in 100 words", "Why do you want this fellowship?"): { question, answer, tags, project_id (optional), word_count, updated_at }. Members add them by hand in Phase 2; in Phase 5 the extension offers to save answers typed into forms.

### API (member, `/api/app`)

```ts
// GET  /profile            -> Profile   (created empty on first read)
// PUT  /profile            <- Profile (full replace, validated) -> Profile
type Profile = {
  given_name: string; family_name: string; preferred_name: string; pronouns: string;
  date_of_birth: string | null; gender: string; nationality: string; country_of_residence: string;
  city: string; address_line1: string; address_line2: string; postal_code: string;
  email: string; phone: string; linkedin_url: string; website_url: string; github_url: string;
  other_links: { label: string; url: string }[];
  headline: string; short_bio: string; long_bio: string;
  education: { institution: string; qualification: string; field: string; start: string | null; end: string | null; grade: string; country: string }[];
  experience: { organization: string; role: string; start: string | null; end: string | null; current: boolean; location: string; summary: string }[];
  skills: string[]; languages: { language: string; level: "basic" | "conversational" | "fluent" | "native" }[];
  awards: { title: string; issuer: string; year: number | null }[];
  publications: { title: string; venue: string; year: number | null; url: string }[];
  references: { name: string; title: string; organization: string; email: string; phone: string; relationship: string }[];
  sensitive: { national_id: string; passport_number: string; passport_expiry: string | null };  // write: plain; read: masked except last 4 unless ?reveal=1
  completeness: number;   // 0..100, read-only
  updated_at: string;
}

// GET /projects -> Project[];  POST /projects -> Project;  GET/PUT/DELETE /projects/{id}
type Project = {
  id: string; name: string; tagline: string; website_url: string; logo_document_id: string | null;
  stage: "idea" | "prototype" | "early_revenue" | "growth" | "other"; sector: string; country: string; city: string;
  founded_on: string | null; legal_status: string; registration_number: string;
  problem: string; solution: string; target_customers: string; market_size: string; business_model: string;
  competition: string; traction: string; impact: string; why_now: string;
  team: { name: string; role: string; bio: string; email: string; linkedin_url: string; is_founder: boolean; gender: string }[];
  team_size: number | null; women_led: boolean; youth_led: boolean;
  revenue_last_12_months: string; funding_raised: string; amount_sought: string; currency: string; use_of_funds: string;
  document_ids: string[];
  custom_fields: { label: string; value: string }[];
  completeness: number; created_at: string; updated_at: string;
}

// GET /documents?kind=&project_id= -> Document[]
// POST /documents (multipart: file, kind, title, project_ids[] optional, is_default optional) -> Document
// PATCH /documents/{id} <- {title?, kind?, project_ids?, is_default?} -> Document
// DELETE /documents/{id};  GET /documents/{id}/download -> the file (owner only)
type Document = { id: string; kind: string; title: string; filename: string; content_type: string;
  size_bytes: number; project_ids: string[]; is_default: boolean; created_at: string }
// GET /documents/usage -> { used_bytes: number; limit_bytes: number }

// GET /answers?q=&project_id= -> Answer[];  POST /answers;  PUT/DELETE /answers/{id}
type Answer = { id: string; question: string; answer: string; tags: string[]; project_id: string | null;
  word_count: number; updated_at: string }
```

Deleting the account deletes all of these, files included. Admins get no route to any of it, matching the rule that staff never read members' applications.

### Member app screens

A new **Apply kit** item in the sidebar (between To-dos and Scans) with tabs **Profile**, **Projects**, **Documents** and **Answers**:

- Profile: sectioned form (same row-and-group pattern as Settings), autosave, a completeness meter, repeatable groups for education, experience and references.
- Projects: a list of project cards; a project page with sections (Basics, Story, Team, Money, Documents, Custom fields), autosave and completeness.
- Documents: drop zone, list with kind, size and default marker, rename, retag, link to projects, download, delete, and the storage meter.
- Answers: searchable list, editor with a live word count.
- Empty states explain the point: "Fill this once. The Blesser extension uses it to fill application forms for you."

---

## 3. Autofill engine (API)

`POST /api/app/autofill/fill`, called by the extension:

```ts
type FillRequest = {
  page: { url: string; title: string; host: string };
  use: { profile: boolean; project_id: string | null };
  fields: {
    key: string;                       // stable id the extension assigns
    tag: "input" | "textarea" | "select" | "contenteditable";
    type: string;                      // text, email, tel, date, file, radio, checkbox, number, url...
    name: string; id: string; autocomplete: string; label: string; placeholder: string;
    help_text: string; section: string;          // nearby legend/heading text
    options: { value: string; label: string }[]; // select, radio, checkbox groups
    required: boolean; max_length: number | null; word_limit: number | null;
    accept: string;                    // for file inputs
  }[];
}
type FillResponse = {
  fills: { key: string; value: string | string[] | null; document_id: string | null;
    source: "profile" | "project" | "answer" | "document" | "drafted";
    confidence: "high" | "medium" | "low"; note: string }[];
  unfilled: { key: string; reason: string }[];
  matched_opportunity_id: string | null;   // tracked application whose link matches page.url
  usage: { drafted_fields: number; remaining_today: number };
}
```

How it fills, cheapest first:

1. **Deterministic matching**: `autocomplete` tokens, input `type`, and a synonym table over label/name/placeholder (e.g. "surname", "last name", "family name" -> `family_name`; "startup name", "company name", "venture" -> `project.name`). Options for selects and radios are matched by normalized label, with country and date-format helpers.
2. **Documents**: file inputs get the default document of the kind the label implies ("CV", "résumé" -> `cv`; "pitch deck" -> `pitch_deck`), respecting `accept`.
3. **Answer library**: free-text questions are matched to saved answers by normalized-question similarity (trigram, Postgres `pg_trgm`), within the word limit.
4. **Drafting**: remaining free-text questions go to the configured model in **one batched call** per request, with only the selected profile/project facts as context. Rules: use only the given facts, never invent numbers, names or dates, respect word and character limits, return null when the facts don't cover it. Drafted values are marked `drafted` and highlighted by the extension for review. Capped per member per day (`AUTOFILL_DRAFTS_PER_DAY`, default 60 fields), counted in `usage`.
5. Sensitive fields (ID, passport) fill only from deterministic matches and are never in model context.

Nothing is stored about the form except a usage counter, plus `matched_opportunity_id` so the extension can offer "Mark as applied".

### Extension authentication

- New token audience `ext`. Access tokens as for `app`; refresh tokens last 90 days, rotate on use, and are revocable.
- Connect flow: the extension opens `{APP_URL}/connect/extension?state=...`; a signed-in member clicks **Allow**; the app calls `POST /api/app/extension/connect` and hands the tokens to the extension with `chrome.runtime.sendMessage(EXTENSION_ID, ...)` (`externally_connectable` limited to the app origin). No password ever enters the extension.
- `GET /api/app/extension/sessions` and `DELETE /api/app/extension/sessions/{id}` back a **Connected browsers** list in Settings → Account and security.
- `/api/app/autofill/*`, `/api/app/profile`, `/api/app/projects`, `/api/app/documents` (read and download) and `/api/app/applications` (read, and `PATCH /applications/{id}` to mark applied) accept `ext` tokens; everything else rejects them.

```ts
// POST /api/app/extension/connect        (app token) <- { name: string }  e.g. "Chrome on Linux"
//   -> 201 { access_token: string; refresh_token: string; session: ExtensionSession }
// POST /api/app/extension/refresh        (no auth)  <- { refresh_token } -> { access_token, refresh_token }  (rotates)
// POST /api/app/extension/logout         (ext token) <- { refresh_token } -> 204
// GET  /api/app/extension/me             (ext token) -> { user: { id, email, display_name }, projects: { id, name, tagline }[],
//                                                         drafting: { enabled: boolean; remaining_today: number } }
// GET  /api/app/extension/sessions       (app token) -> ExtensionSession[]
// DELETE /api/app/extension/sessions/{id} (app token) -> 204; that session's tokens stop working at once
type ExtensionSession = { id: string; name: string; created_at: string; last_used_at: string | null }
```

`FillRequest` also accepts `allow_drafting: boolean` (default true); when false, step 4 is skipped.

---

## 4. Browser extension

- `extension/` npm workspace: TypeScript, Vite, Manifest V3, React for the popup using `@blesser/ui` tokens. Chrome and Edge first; Firefox in Phase 5.
- **Permissions**: `activeTab`, `scripting`, `storage`. No `<all_urls>` at install; the content script is injected on demand when the member clicks **Fill this page**, and `all_frames` covers same-origin and embedded form frames on that tab. Optional host permissions only if a later adapter needs them.
- **Popup**: signed-in state; "Fill as" picker (**Me** or a project, e.g. **Siwa**, which also uses the profile for personal fields); **Fill this page**; results: "18 filled, 3 drafted for review, 2 need you", with **Show what's left**; **Mark as applied** when the page matches a tracked application; a link to the Apply kit to fill gaps.
- **Content script**:
  - Collects fields: labels from `<label for>`, wrapping labels, `aria-labelledby`, `aria-label`, placeholder, fieldset legend and nearby headings; option lists; required flags; `maxlength`; word limits parsed from help text ("max 200 words").
  - Fills like a person: native value setters plus `input`, `change` and `blur` events, so React, Vue and Angular forms register the values. Handles selects, radio and checkbox groups, dates, contenteditable editors, and file inputs (downloads the document with the extension token and attaches it via `DataTransfer`).
  - Marks every filled field with a subtle outline; drafted fields get a distinct outline and a small "Drafted by Blesser, review" tag; unfilled required fields are listed in the popup and can be jumped to.
  - **Never submits**, never clicks buttons, never fills password or payment fields, and never runs on pages the member did not ask it to.
  - Multi-page forms: the member clicks Fill again on each page.
- Known limits for v1: cross-origin frames the browser blocks, CAPTCHA, fully custom widgets that ignore input events, Typeform-style one-question-per-screen flows (filled one screen at a time). Google Forms, Microsoft Forms, Airtable, Submittable, Greenhouse, Lever, Workable and plain HTML forms are the test set.
- Distribution: unpacked for development, then the Chrome Web Store and Edge Add-ons. The store listing needs a privacy policy covering the data above; the site's privacy page gets a section on the applicant kit and the extension.

---

## Decisions taken (change any of them)

1. Share images render on the public site's server (Satori), so the art component and fonts are reused, and public pages get Open Graph images for free.
2. Members-only opportunities can be shared; the link shows a teaser and asks the visitor to sign up to see the official link.
3. Captions come from templates, not a model: free, instant and never invent anything.
4. Files live on local disk (Docker volume) until there is a reason for object storage.
5. ID and passport numbers are encrypted at rest and never sent to the model.
6. The extension fills and highlights; the member always reviews and submits.
7. Drafting free-text answers uses the platform model with a daily cap per member.
8. Chrome and Edge first.

## Open questions for the owner

- The extension's name in the store (working: "Blesser: Apply with your kit").
- Whether drafting with the model should be on by default or opt-in per fill.
- Whether to count referral sign-ups from share links and show members how many people they brought in.

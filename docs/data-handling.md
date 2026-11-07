# Data handling: what we store, and what reaches third parties

This is the plain-language account of where your data lives, for how
long, and exactly which parts are sent to outside services. The same
summary appears in the app under **Settings → Preferences → Data & AI
providers** and next to CV uploads.

## What is stored, and where

| Data | Where | Kept until |
|---|---|---|
| Account (email, bcrypt password hash, display name, profile picture) | Postgres `users` | you delete the account |
| Sessions (hashed refresh tokens) | Postgres `auth_refresh_tokens` | sign-out, expiry, password reset, or account deletion |
| Runs, schools, programmes, professors, papers, scores, drafts, applications, chats, agent/tool settings | Postgres, every row owned by your account | you delete them, or the account |
| Index of professors your runs looked up, matched or not (OpenAlex author and works) | Postgres `professor_index`, owned by your account | the account is deleted; reused only while `PROFESSOR_INDEX_DAYS` old or newer |
| Documents (CVs, statements): their Markdown text, tailored versions and suggestions | Postgres `cv_documents`, `cv_tailored_versions`, `cv_suggestions` | you delete the document, or the account |
| The file you uploaded (`.docx`, `.pdf`, `.md` or `.txt`), kept for download | API server disk under `CV_STORAGE_DIR/cv/<document id>/` | you delete the document, or the account |
| CV edits not yet synced, and unsaved CV variants (#210) | Your browser's localStorage, keyed by account | the edit syncs (unsaved variants: you save or discard them); sign-out does not clear them |
| Your model provider API keys | Postgres `provider_configs` | you remove them, or the account |
| Notifications (inbox), push subscriptions (one per browser: its push service URL and encryption keys), notification settings | Postgres `notifications`, `push_subscriptions`, `notification_preferences` | you delete the account; signing out removes that browser's subscription |
| Data-export archives (a ZIP of every row and CV file) | API server disk under `CV_STORAGE_DIR/exports/<account id>/` | 7-day expiry (swept by the worker every minute), or account deletion |

* **Deleting your account removes all of it in one step:** every row
  cascades from the user row, and uploaded CV files and every export
  archive are removed from disk right after (`auth/service.py:
  delete_account`). The worker also deletes any export directory whose
  account no longer exists.
* API keys are never sent back to the browser (the UI only learns
  *whether* a key is set). They are encrypted at rest with `SECRETS_KEY`
  (or a key derived from `AUTH_SECRET`); with neither set they are stored
  in plaintext, so production must set one.
* Profile pictures are re-encoded server-side, which strips EXIF/GPS
  metadata before anything is stored.
* **Agent traces** (tool-call payloads up to 20 KB each, the task log and
  resume checkpoint) are deleted `TRACE_RETENTION_DAYS` (default 90) after
  a task finishes, by the worker's housekeeping loop. Results stay.
* **Sign-up consent:** accounts record when they accepted the Terms and
  the Privacy notice (`/terms`, `/privacy`) and which version
  (`TERMS_VERSION`).

## People Graduator researches

Professors are not users. Their public academic information (name,
institution, publications, profile and lab links, photo and bio from
faculty pages, sometimes an email) is stored in the accounts of the
students who research them. The Privacy notice tells them how to ask for
removal. To act on a request:

```
make remove-professor ARGS='--openalex-id https://openalex.org/A123'
make remove-professor ARGS='--name "Ada Lovelace" --school "ETH Zurich"'
```

This deletes every matching professor record in every account (with
papers, candidate scores, drafts and professor index entries) and records
an opt-out in
`professor_optouts`; later saves and research tasks for that person are
refused.

> These notices and controls are a starting point, not legal advice. Have
> counsel review the Terms, the Privacy notice and the professor-data
> handling before a public launch.

## What reaches third-party providers

Nothing is sent anywhere unless a feature you use needs it. Providers
are whatever you (or the server operator) configure: Anthropic, OpenAI,
Gemini, Ollama or any OpenAI-compatible endpoint for models; Voyage,
OpenAI, Gemini or Ollama for embeddings (or a local TF-IDF fallback that
sends nothing).

| Feature | Provider | What is sent |
|---|---|---|
| Research runs | LLM provider | your interest statement, degree/region/field, and the web pages, faculty listings and paper metadata the agent reads |
| Research runs | Search (Tavily, Brave; DuckDuckGo only if the operator lists it in `SEARCH_PROVIDERS`) | search queries the agent writes: school/programme/faculty names, and phrases that can paraphrase your interest statement |
| Research runs | OpenAlex | professor names and institution hints (with the operator's `OPENALEX_MAILTO` contact) |
| Research runs | University and lab websites, fetched directly | a request for the page, identified as `GraduatorBot` (`FETCH_USER_AGENT`); `robots.txt` is honoured |
| Research runs | Internet Archive (`web.archive.org`) | the URL of a page that couldn't be fetched directly (`FETCH_FALLBACKS`) |
| Fit scoring | Embedding provider | your interest statement and paper abstracts |
| Rationale check (opt-in, operator setting) | Typesafe | the match rationale and the cited paper titles |
| Gradis chat | LLM provider | your messages, the page context chips you leave on, and results of tools it calls. **CV content:** when Gradis reads a CV, the CV's Markdown, up to 20,000 characters per read |
| CV tailoring with Gradis | LLM provider | the CV version it is tailoring (same limit) and the professor's dossier |
| Browser push notifications (if you turn them on) | Your browser vendor's push service (Google, Mozilla, Apple) | what happened and an in-app link, e.g. "Your run Machine Learning in Canada finished: 12 candidates". Never CV text, drafts or professor details ([notifications.md](notifications.md)) |
| "Suggest from my CV" on New run | LLM provider | text from your CV's summary, research, projects, publications and education sections (≤400 characters per paragraph or bullet, ≤60 of them). Only when you press the button |

**Never sent:** your password, other accounts' data, your API keys
(except to the provider they belong to), or whole CV files. Emails are
never sent to professors: drafts stay drafts.

## Limits that protect your account

Per-account throttles cap runaway loops (scripts, stuck retries) with a
clear "Too many …, try again in N" message and a `Retry-After` header:

| Bucket | Burst | Sustained |
|---|---|---|
| Uploads (CVs, profile pictures) | 10 / minute | 60 / hour |
| Gradis chat turns | 15 / minute | 300 / hour |
| CV suggestions | 20 / minute | 200 / hour |
| Research requests (new runs, draft requests, added schools/professors, task retries) | 10 / minute | 100 / hour |

Read-only lookups never count toward a run's research allowance. Limits live in `api/core/ratelimit.py`; they are
held in API process memory, which suits the single-process deployment.

# Notifications

Graduator tells you when something needs you, without the tab open
(#196): an in-app inbox (the bell in the header), browser push, and
email. Code: `api/api/notifications/`, the worker loops in
`api/api/runs/queue.py`, and in the web app `public/sw.js`,
`src/lib/push.ts`, `components/layout/NotificationBell.tsx` and
Settings > Notifications.

## Events

| Event (`kind`) | Where it starts | Default channels |
|---|---|---|
| Run finished, with candidate count (`run_finished`) | `note_tasks_drained` flips the run to done (`runs/lifecycle.py`) | inbox + push |
| First candidate saved (`first_candidate`) | first `candidate_scores` insert of a run (`prospects/tools.py`) | inbox |
| Run paused: out of model allowance (`run_paused`) | `_park_for_allowance` (`runs/queue.py`) | inbox + push |
| Run needs attention (`run_attention`) | a task concluded `error` for good | inbox |
| Email drafts ready (`drafts_ready`) | the last open `draft_email` task of a run finishes | inbox + push |
| Application deadline in 14 / 7 / 1 days (`deadline`) | the daily deadline check | inbox + push + email |

Every event and channel can be turned off in Settings > Notifications
(global preferences; no per-run toggle yet). Reminder days are fixed.

## Create once, deliver separately

An event site calls `notify()` inside the transaction of the change that
caused it. It inserts one `notifications` row with
`ON CONFLICT DO NOTHING` on `(user_id, dedupe_key)`, so a retried task or
a second reaper pass can't notify twice, and a rolled-back change never
notifies. Dedupe keys:

* `run:{id}:done:{research task count}`: once per finish; drafts reopening
  and closing a run don't re-announce it, more research does.
* `run:{id}:first_candidate`.
* `run:{id}:paused:{task}:{attempt}`, created only by the attempt whose
  conditional `UPDATE runs ... WHERE status = 'running'` flipped the run,
  so several tasks refused together notify once.
* `run:{id}:attention:{day}`: at most one a day per run.
* `drafts:{task}:{attempt}`, behind a per-run advisory lock so the last of
  two draft tasks finishing together still sees the other one done.
* `app:{id}:{days}:{deadline date}`: moving a deadline re-arms its
  reminders.

Delivery happens after commit, in the worker's `delivery_loop`. It wakes
on a `"<user_id>:notifications"` payload on the existing
`graduator_run_events` channel (the run feed ignores it) and polls every
`NOTIFICATION_DELIVER_SECONDS` (30) as a backstop. It claims undelivered
rows with `FOR UPDATE SKIP LOCKED`, then for each:

* **Quiet hours** (local `HH:MM` window in the account's timezone; a start
  after the end runs past midnight): push and email wait until the window
  ends. The inbox fills as usual.
* **Rate cap:** past `NOTIFICATION_HOURLY_CAP` (20) push/email sends per
  account in the last hour, a row is marked `capped` and stays inbox-only.
* **Push** goes to every subscribed device of the owner. A `404` or `410`
  from the push service deletes that subscription.
* **Email** goes to verified addresses only, through `core/mailer.py`,
  with a per-kind unsubscribe link (a signed 90-day token; the web page
  `/notifications/unsubscribe` asks for one click, so mail scanners
  opening links don't unsubscribe anyone).

`notifications.delivery` records what happened: `push`, `email`,
`push,email`, `none` or `capped`.

## Application deadlines

`applications.deadline` stays free text (agents save what admissions
pages say). `applications.deadline_date` is the schedulable copy: the
tracker form sends the picked date, and otherwise the server parses the
text when it names one date unambiguously (`applications/dates.py`:
ISO, "15 December 2026", "Dec 15, 2026", d/m/y only when the day is over
12). Migration 041 ran the same parse once over existing rows.

The worker's reaper runs the check hourly. For applications in
`wishlist` or `applying` (submitted or later stops reminders), it counts
days to the deadline in the owner's timezone from 08:00 local time, and
creates the reminder for the smallest threshold not yet passed: a
reminder missed while no worker ran goes out late rather than never. The
web app reports the browser's timezone the first time the bell loads
(UTC until then); it can be changed in Settings.

## Email digest

Off by default (email is on by default only for deadlines). When on, the
same hourly pass sends one email a day from 08:00 local time listing the
account's unread inbox notifications from the last day that didn't
already go out by email. Available on every plan while plans are off.

## Browser push

Web Push with VAPID, sent from the worker with `pywebpush`
(`notifications/push.py`; the send is one function tests stub).

```
make vapid-keys             # prints the three lines below
VAPID_PUBLIC_KEY=...        # base64url, uncompressed P-256 point
VAPID_PRIVATE_KEY=...       # base64url, raw 32-byte key
VAPID_SUBJECT=mailto:ops@yourdomain
```

Set them in `api/.env` for both the API and the worker. Generate the pair
once per deployment: a new pair invalidates every browser's
subscription. With either key unset, push is off and the worker logs it
once; the inbox and email still work. `npx web-push generate-vapid-keys`
produces the same format.

**Privacy:** a push payload is `{id, kind, title, body, link}`: what
happened plus an in-app link ("Your run Machine Learning in Canada
finished: 12 candidates"). No CV text, draft content or professor details:
payloads pass through the browser vendor's push service. Event builders in
`notifications/events.py` keep to this, and tests check it.

**Devices:** one `push_subscriptions` row per browser; an endpoint belongs
to one account (subscribing from another account moves it). Signing out
sends the browser's endpoint with the logout, which deletes that row, and
the browser unsubscribes too. Subscriptions are not in data exports.

**Asking permission:** never on page load. A running run shows "Notify me
when it's done?" (dismissible, remembered per browser), and Settings >
Notifications has a Turn on button, a test button and the device list. On
iPhone and iPad, web push works only for a site added to the Home Screen
(iOS 16.4+), so both places explain that instead of offering the button.
The web app ships a service worker (`/sw.js`, push and click handling
only, no offline cache; nginx serves it `no-cache`) and a web manifest.

## Inbox feed

The bell polls `GET /api/notifications` every 60 seconds and on window
focus (react-query), and a push arriving while a tab is open refreshes it
at once. It holds no LISTEN connection, so it doesn't add to the per-
process stream limit the run feed has.

## API

| Route | |
|---|---|
| `GET /api/notifications` | newest 30, unread count, stored timezone |
| `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all` | mark read |
| `GET`/`PATCH /api/notifications/preferences` | channels per kind, quiet hours, timezone, digest |
| `GET /api/notifications/push/config` | whether push is on, and the VAPID public key |
| `GET`/`POST`/`DELETE /api/notifications/push/subscriptions` | this account's devices |
| `POST /api/notifications/test` | test notification, pushed at once (rate-limited) |
| `POST /api/notifications/unsubscribe` | the email link (no sign-in; signed token) |

## Follow-ups

* More events: Gradis replies to a long request, CV render finished, usage
  close to a plan cap.
* A per-run "Notify me" toggle and user-set reminder days.
* A shared LISTEN per process if the inbox ever moves to SSE.

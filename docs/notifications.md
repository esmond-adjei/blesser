# Notifications

Blesser tells people when something needs them, without the tab open: an in-app inbox (Notifications in the sidebar, with an unread count), browser push, and email. Code: `api/api/notifications/`, the worker loops in `api/api/scans/queue.py`, and in the web app `public/sw.js`, `src/lib/push.ts`, the inbox page `pages/Notifications.tsx` (mark read, select and delete, clear all), the unread count in `components/layout/Shell.tsx` and Settings > Notifications (`components/settings/NotificationsPanel.tsx`).

## Events

| Event (`kind`) | Where it starts | Default channels |
|---|---|---|
| Application deadline in 14 / 7 / 1 days (`deadline`) | the hourly deadline check | inbox + push + email |
| Scan finished, with how many opportunities it added (`scan_finished`) | the scan's last task concludes (`scans/service.py`) | inbox + push |
| Scan needs attention (`scan_attention`) | a task fails for good | inbox |

Every event and channel can be turned off in Settings > Notifications. Reminder days are fixed. The test buttons in Settings create a `test` notification, which ignores preferences, quiet hours and the rate cap.

## Create once, deliver separately

An event site calls `notify()` inside the transaction of the change that caused it. It inserts one `notifications` row with `ON CONFLICT DO NOTHING` on `(user_id, dedupe_key)`, so a retried task can't notify twice and a rolled-back change never notifies. Dedupe keys:

* `app:{id}:{days}:{deadline date}`: moving a deadline re-arms its reminders.
* `scan:{id}:done:{task count}`.
* `scan:{id}:attention:{day}`: at most one a day per scan.

Delivery happens after commit, in the worker's delivery loop. It wakes on a `"<user_id>:notifications"` payload on the `blesser_events` channel and polls every `NOTIFICATION_DELIVER_SECONDS` (30) as a backstop. For each undelivered row:

* **Quiet hours** (a local `HH:MM` window in the account's timezone): push and email wait until the window ends. The inbox fills as usual.
* **Rate cap:** past `NOTIFICATION_HOURLY_CAP` (20) push and email sends per account in the last hour, a row stays inbox-only.
* **Push** goes to every subscribed device. A `404` or `410` from the push service deletes that subscription.
* **Email** goes to verified addresses only, with a per-kind unsubscribe link (a signed token; the page asks for one click, so mail scanners opening links don't unsubscribe anyone).

## Application deadlines

`applications.deadline` is free text; `applications.deadline_date` is the schedulable copy. The tracker sends the picked date, and otherwise the server parses the text when it names one date unambiguously (`applications/dates.py`).

The worker checks hourly. For applications that are `saved` or `preparing` (submitted or later stops reminders), it counts days to the deadline in the owner's timezone from 08:00 local time and creates the reminder for the smallest threshold not yet passed, so a reminder missed while no worker ran goes out late rather than never. The web app reports the browser's timezone the first time the app shell loads the inbox while none is stored; it can be changed in Settings.

## Email digest

Off by default. When on, the same hourly pass sends one email a day from 08:00 local time listing unread inbox notifications from the last day that didn't already go out by email.

## Browser push

Web Push with VAPID, sent from the worker with `pywebpush`.

```
make vapid-keys             # prints the three lines below
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:ops@yourdomain
```

Set them in `api/.env` for both the API and the worker, once per deployment: a new pair invalidates every browser's subscription. With either key unset, push is off; the inbox and email still work.

A push payload is `{id, kind, title, body, link}`, with no focus notes or other personal text, because it passes through the browser vendor's push service. Settings > Notifications has the Turn on button, a test button and the device list. On iPhone and iPad, web push works only once the site is added to the Home Screen (iOS 16.4+).

## API

Member routes live under `/api/app`.

| Route | |
|---|---|
| `GET /api/app/notifications` | newest 30, unread count, stored timezone |
| `POST /api/app/notifications/{id}/read`, `POST /api/app/notifications/read-all` | mark read |
| `DELETE /api/app/notifications/{id}` | delete one |
| `DELETE /api/app/notifications?ids=...` | delete the named entries, or the whole inbox when `ids` is absent |
| `GET`/`PATCH /api/app/notifications/preferences` | channels per kind, quiet hours, timezone, digest |
| `GET /api/app/notifications/push/config` | whether push is on, and the VAPID public key |
| `GET`/`POST`/`DELETE /api/app/notifications/push/subscriptions` | this account's devices |
| `POST /api/app/notifications/test` | a test push to every device now (rate-limited) |
| `POST /api/app/notifications/test-email` | a test email to the verified address now (rate-limited) |
| `POST /api/app/notifications/unsubscribe` | the email link (no sign-in; signed token) |

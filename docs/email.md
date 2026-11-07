# Transactional email

Used for password reset and email verification (#35), and for
notification emails (deadline reminders, the optional daily digest; see
[notifications.md](notifications.md)). Never used to contact professors:
outreach drafts are never sent.

## Decision: SMTP relay to a transactional provider

`api/core/mailer.py` speaks plain SMTP (STARTTLS). Every mainstream
transactional provider offers an SMTP relay, so the provider is a
configuration choice, not code:

| Provider | Free tier | Paid (approx.) | Notes |
|---|---|---|---|
| **Postmark** (recommended) | 100 emails/month | from $15/month for 10k | best deliverability for transactional-only traffic; bounce + spam webhooks |
| Amazon SES | 3,000/month for 12 months (from EC2) | $0.10 per 1,000 | cheapest at scale; needs domain verification + sandbox exit |
| Resend | 3,000/month | from $20/month for 50k | simple setup, good DX |

Beta volume (sign-ups, occasional resets) fits every free tier. Pick
Postmark for deliverability; SES if cost dominates later.

Before enabling in production:

1. Verify the sending domain (SPF, DKIM, and a DMARC policy).
2. Point bounce/complaint webhooks at the provider dashboard (we don't
   ingest them yet; a bounced verification simply never completes).
3. Send a test reset from **staging** and confirm the link host
   (`APP_BASE_URL`) is right.

## Configuration

```
MAIL_BACKEND=smtp            # "console" prints mail to the API's stderr (dev default)
MAIL_FROM="Graduator <no-reply@yourdomain>"
SMTP_HOST=smtp.postmarkapp.com
SMTP_PORT=587
SMTP_USERNAME=<server token>
SMTP_PASSWORD=<server token>
SMTP_STARTTLS=true
APP_BASE_URL=https://app.yourdomain   # links in emails point here
```

## Flows

* **Reset:** `POST /api/auth/password/forgot` always returns the same
  message (no account enumeration; mail is sent in the background so
  timing matches). Throttled per email (3 per 15 min) and per IP. Links
  are single-use, expire in 30 minutes, and using one revokes every
  session and burns other outstanding reset links.
* **Verification:** sent on registration; resend has a 60 s cooldown.
  Policy is **verify-to-unlock-sensitive-actions**: the app works
  unverified (with a banner), while sensitive actions (data export,
  account linking) call `email_flows.require_verified`.

Tokens are random, stored only as SHA-256 hashes (`auth_email_tokens`),
and removed with the account.

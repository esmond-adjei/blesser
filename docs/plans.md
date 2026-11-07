# Plans and paywalls

## Plan model (source of truth: `api/billing/plans.py`)

| | Free | Pro |
|---|---|---|
| Research runs per month | 3 | 30 |
| Model tokens per month (metered, #33) | 2M | 20M |
| Professors scored per run | 30 | 100 |
| Auto (the system model) tokens per day | 500k | unlimited |
| Gradis chat, CV studio, data export | ✓ | ✓ |
| Interest suggestions from your CV | – | ✓ |

Prices are set at launch. **Beta:** while `BILLING_ENFORCED=false` (the
default) every account resolves to the `beta` plan: every feature, no
quotas, so nobody is affected until launch pricing lands.

Free and Pro also carry the operator's daily ceilings on the shared key:
the plan's `system_tokens_per_day` on Auto and `SYSTEM_DAILY_TOOL_CALLS`
across search, scoring and verification. Beta has neither, so a beta
account is never paused by them.

Quotas reset at 00:00 UTC on the 1st. Token usage comes from the
metering rollups, so the plan view and `/api/usage` always agree.

**Auto** is the default for runs, chat and interest suggestions (#153):
the system model on the operator's key. Its daily allowance is per plan
(`Plan.system_tokens_per_day`; `None` follows `SYSTEM_MODEL_DAILY_TOKENS`,
`0` is unlimited) and shows on the Auto choice in every model picker.
Beta is exempt from daily ceilings, so pre-launch Auto has no allowance.
People's own models never become the default by being configured: only a
run or chat that picks one, or the "Use my model by default" setting,
uses them.

## Trying each plan in development

Set `BILLING_PLAN_SWITCH=true` and Settings → Usage shows a plan picker
on the plan card (`PUT /api/billing/plan {"plan": "free"}` does the
same). The picked plan is stored on the account and applies even while
`BILLING_ENFORCED=false`, so each gate and quota can be tried as Free,
Pro or Beta. With the switch on, accounts that never picked a plan are on
their stored plan (Free by default), not Beta. Never enable it where
real users sign up: anyone could give themselves Pro.

## Picking a plan and checkout

Once plans apply (`BILLING_ENFORCED=true`, or the development switch),
a new account is sent to `/plans` before anything else (`needs_plan` on
the user, from `users.plan_selected_at`); existing accounts were
backfilled as having picked. Settings → Usage links there to change plan.

* Free applies at once (`POST /api/billing/checkout {"plan": "free"}`).
* A paid plan returns a checkout session; `/billing/checkout` takes the
  payment and `POST /api/billing/checkout/complete` applies the plan,
  which is the webhook's job once Stripe is wired in.

`BILLING_PROVIDER=simulated` (the only provider so far, and
development-only) takes no real payment. It also requires the
development switch (`BILLING_PLAN_SWITCH=true`); otherwise paid checkout
is refused with a 400 and only Free applies. Test cards: `4242 4242 4242
4242` succeeds, `4000 0000 0000 0002` is declined; any future expiry and
CVC. Leave `BILLING_PROVIDER` empty in any deployment real users can
reach. Pro's $12/month is a placeholder until launch pricing
(`monthly_price_usd` in `plans.py`).

## Enforcement (one primitive)

`api/billing/service.py`:

* `require_feature(session, user_id, key)`: plan includes the feature, else 402.
* `check_quota(session, user_id, key)`: within the monthly quota, else 402.
* `gate_new_run(...)`: run quota + clamps the per-run professor budget.

A 402 always carries `{"code": "upgrade_required", kind, key, label,
noun, plan, upgrade_to, used?, limit?, message}`. The webapp's single
`UpgradePrompt` opens on any such response, from JSON calls or the chat
stream, and links to Settings → Usage, where the plan card shows limits
and this month's use. New gates call the primitive; no ad-hoc checks.

Gated today: run creation (runs/month, per-run cap), Gradis chat turns
(token allowance), data export (feature). Research tasks already
running finish; the token gate applies to new work.

## Billing work this unlocks (not built yet)

1. Stripe Checkout for Pro (monthly/annual) and the Customer Portal for
   plan changes, cancellation and invoices.
2. Webhook endpoint (`checkout.session.completed`,
   `customer.subscription.updated/deleted`) that sets `users.plan`.
   Idempotent, signature-verified.
3. Grace handling for failed payments (keep Pro N days, then Free).
4. Flip `BILLING_ENFORCED=true` at launch; announce limits to beta users
   beforehand (the plan card already shows them).

import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { Check, CheckCircle2, CreditCard, FlaskConical } from "lucide-react"
import * as api from "../lib/api"
import { apiMessage } from "../lib/api"
import { useAuth } from "../lib/auth"
import { cn } from "../lib/utils"
import { Button } from "../components/ui/button"
import { Field, Input } from "../components/ui/input"
import { Alert, AlertDescription, Skeleton } from "../components/ui/feedback"
import { AppLogo } from "../components/layout/AppLogo"

/** Only same-app paths: ?next= must never send the user off-site. */
function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/opportunities"
}

const fmtLimit = (n: number) =>
  n >= 1_000_000 ? `${n / 1_000_000}M` : n.toLocaleString()

const price = (usd: number) => (usd > 0 ? `$${usd}` : "$0")

function PlansShell({
  title,
  subtitle,
  narrow = false,
  children,
}: {
  title: string
  subtitle: string
  narrow?: boolean
  children: React.ReactNode
}) {
  return (
    <div className={cn("mx-auto flex min-h-dvh w-full flex-col justify-center gap-6 p-4 sm:p-6", narrow ? "max-w-sm" : "max-w-3xl")}>
      <div className="flex items-center gap-2.5">
        <AppLogo className="size-9" />
        <div>
          <p className="text-lg font-bold tracking-tight">{title}</p>
          <p className="type-caption">{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  )
}

/** After a plan change: the session's user and every plan reader refresh. */
function useAfterPlanChange() {
  const { updateUser } = useAuth()
  const queryClient = useQueryClient()
  return React.useCallback(async () => {
    updateUser(await api.getMe())
    await queryClient.invalidateQueries({ queryKey: ["plan"] })
  }, [updateUser, queryClient])
}

/** Plan picker for onboarding and plan changes. Free applies at once; paid plans go to checkout. */
export function PlanPicker() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const next = safeNext(searchParams.get("next"))
  const afterChange = useAfterPlanChange()
  const { data: summary, error: loadError } = useQuery({ queryKey: ["plan"], queryFn: api.getPlan })
  const [busy, setBusy] = React.useState<string | null>(null)
  const [err, setErr] = React.useState<string | null>(null)
  const onboarding = !!user?.needs_plan

  async function choose(planId: string) {
    setBusy(planId)
    setErr(null)
    try {
      const out = await api.startCheckout(planId)
      if (out.status === "applied") {
        await afterChange()
        navigate(next, { replace: true })
      } else {
        navigate(`/billing/checkout?session=${encodeURIComponent(out.session)}&next=${encodeURIComponent(next)}`)
      }
    } catch (e) {
      setErr(apiMessage(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <PlansShell
      title={onboarding ? "Choose your plan" : "Change plan"}
      subtitle={onboarding ? "You can change it any time in Settings › Usage." : "Your new plan applies straight away."}
    >
      {loadError ? (
        <Alert variant="destructive">
          <AlertDescription>{apiMessage(loadError)}</AlertDescription>
        </Alert>
      ) : !summary ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      ) : !summary.enforced ? (
        <div className="space-y-4">
          <p className="type-meta">Plans don't apply on this server: everything is included during beta.</p>
          <Button onClick={() => navigate(next, { replace: true })}>Continue</Button>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            {summary.catalog.map((offer) => {
              const current = !onboarding && summary.plan.id === offer.id
              return (
                <section
                  key={offer.id}
                  className={cn(
                    "flex flex-col rounded-xl border bg-card p-5",
                    offer.monthly_price_usd > 0 ? "border-primary/40" : "border-border",
                  )}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <h2 className="text-base font-semibold">{offer.label}</h2>
                    {current && (
                      <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">Current plan</span>
                    )}
                  </div>
                  <p className="mt-2">
                    <span className="text-3xl font-semibold tabular-nums tracking-tight">{price(offer.monthly_price_usd)}</span>
                    <span className="type-meta"> / month</span>
                  </p>
                  <ul className="mt-4 flex-1 space-y-1.5 text-sm">
                    {offer.quotas.map((q) => (
                      <li key={q.key} className="flex gap-2">
                        <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                        <span>
                          {q.limit == null ? "Unlimited" : fmtLimit(q.limit)} {q.label.toLowerCase()}
                        </span>
                      </li>
                    ))}
                    {offer.features.map((f) => (
                      <li key={f} className="flex gap-2">
                        <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                  <Button
                    className="mt-5 w-full"
                    variant={offer.monthly_price_usd > 0 ? "default" : "outline"}
                    disabled={busy !== null || current}
                    onClick={() => choose(offer.id)}
                  >
                    {busy === offer.id
                      ? "One moment…"
                      : current
                        ? "Your plan"
                        : offer.monthly_price_usd > 0
                          ? `Get ${offer.label}`
                          : `Continue with ${offer.label}`}
                  </Button>
                </section>
              )
            })}
          </div>
          {err && (
            <Alert variant="destructive">
              <AlertDescription>{err}</AlertDescription>
            </Alert>
          )}
          {!onboarding && (
            <p className="text-center text-xs">
              <Link to={next} className="text-muted-foreground hover:underline">
                Keep my current plan
              </Link>
            </p>
          )}
        </>
      )}
    </PlansShell>
  )
}

/** Simulated checkout for paid plans: test cards only, nothing is charged. */
export function Checkout() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const session = searchParams.get("session") || ""
  const next = safeNext(searchParams.get("next"))
  const afterChange = useAfterPlanChange()
  const { data: page, error: loadError } = useQuery({
    queryKey: ["checkout", session],
    queryFn: () => api.getCheckout(session),
    enabled: !!session,
    retry: false,
  })
  const [card, setCard] = React.useState("")
  const [expiry, setExpiry] = React.useState("")
  const [cvc, setCvc] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)
  const [paid, setPaid] = React.useState(false)
  const backToPlans = `/plans?next=${encodeURIComponent(next)}`

  async function onPay(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      await api.completeCheckout(session, card)
      await afterChange()
      setPaid(true)
    } catch (e2) {
      setErr(apiMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  const fail = !session ? "This checkout link is incomplete." : loadError ? apiMessage(loadError) : null

  return (
    <PlansShell title="Checkout" subtitle="Secure payment" narrow>
      <div className="space-y-4">
        {fail ? (
          <>
            <Alert variant="destructive">
              <AlertDescription>{fail}</AlertDescription>
            </Alert>
            <Button variant="outline" className="w-full" onClick={() => navigate(backToPlans)}>
              Back to plans
            </Button>
          </>
        ) : !page ? (
          <Skeleton className="h-80" />
        ) : paid ? (
          <div className="space-y-4 rounded-xl border border-border bg-card p-5 text-center">
            <CheckCircle2 className="mx-auto size-10 text-primary" aria-hidden />
            <div>
              <p className="text-base font-semibold">You're on {page.plan.label}</p>
              <p className="mt-1 type-meta">Payment confirmed. Your new limits apply now.</p>
            </div>
            <Button className="w-full" onClick={() => navigate(next, { replace: true })}>
              Continue
            </Button>
          </div>
        ) : (
          <>
            {page.provider === "simulated" && (
              <div className="flex gap-2.5 rounded-lg bg-caution-soft p-3 text-xs text-label">
                <FlaskConical className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden />
                <p>
                  Test mode: no real payment is taken. Use{" "}
                  <button type="button" className="font-mono underline" onClick={() => setCard(page.test_cards.succeeds)}>
                    {page.test_cards.succeeds}
                  </button>{" "}
                  to succeed or{" "}
                  <button type="button" className="font-mono underline" onClick={() => setCard(page.test_cards.declined)}>
                    {page.test_cards.declined}
                  </button>{" "}
                  to see a decline, with any future expiry and CVC.
                </p>
              </div>
            )}
            <div className="flex items-baseline justify-between rounded-xl border border-border bg-card p-4">
              <div>
                <p className="text-sm font-semibold">Blesser {page.plan.label}</p>
                <p className="type-caption">Billed monthly</p>
              </div>
              <p className="text-lg font-semibold tabular-nums">${page.monthly_price_usd}<span className="text-xs font-normal text-muted-foreground"> / month</span></p>
            </div>
            <form onSubmit={onPay} className="space-y-3">
              <Field label="Card number">
                <Input
                  inputMode="numeric"
                  autoComplete="cc-number"
                  placeholder="1234 1234 1234 1234"
                  required
                  value={card}
                  onChange={(e) => setCard(e.target.value)}
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Expiry">
                  <Input
                    autoComplete="cc-exp"
                    placeholder="MM / YY"
                    required
                    pattern="\d{2}\s?/\s?\d{2}"
                    value={expiry}
                    onChange={(e) => setExpiry(e.target.value)}
                  />
                </Field>
                <Field label="CVC">
                  <Input
                    inputMode="numeric"
                    autoComplete="cc-csc"
                    placeholder="123"
                    required
                    pattern="\d{3,4}"
                    value={cvc}
                    onChange={(e) => setCvc(e.target.value)}
                  />
                </Field>
              </div>
              {err && (
                <Alert variant="destructive">
                  <AlertDescription>{err}</AlertDescription>
                </Alert>
              )}
              <Button type="submit" className="w-full" disabled={busy}>
                <CreditCard aria-hidden /> {busy ? "Processing…" : `Pay $${page.monthly_price_usd}`}
              </Button>
            </form>
            <p className="text-center text-xs">
              <Link to={backToPlans} className="text-muted-foreground hover:underline">
                Cancel and go back
              </Link>
            </p>
          </>
        )}
      </div>
    </PlansShell>
  )
}

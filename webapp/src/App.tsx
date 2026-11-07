import { ProfessorDetailPage } from "./pages/ProfessorDetailPage"
import * as React from "react"
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useParams } from "react-router-dom"
import { ErrorState } from "./components/feedback/EmptyState"
import { buttonVariants } from "./components/ui/button"
import { LoadingScreen } from "./components/feedback/LoadingScreen"
import { AppLogo } from "./components/layout/AppLogo"
import { useAuth } from "./lib/auth"
import { ErrorBoundary } from "./components/feedback/ErrorBoundary"

// The shell is lazy too, so anonymous visitors never download it.
const Layout = React.lazy(() => import("./components/layout/AppShell").then((m) => ({ default: m.Layout })))

// The marketing site lives on its own host.
const SITE_URL = (import.meta.env.VITE_SITE_URL as string | undefined)?.trim()

// Route-level code-splitting keeps the entry chunk small.
const Applications = React.lazy(() =>
  import("./pages/Applications").then((m) => ({ default: m.Applications })),
)
const ProgramProfessors = React.lazy(() =>
  import("./pages/ProgramProfessors").then((m) => ({ default: m.ProgramProfessors })),
)
const GradisPage = React.lazy(() =>
  import("./pages/GradisPage").then((m) => ({ default: m.GradisPage })),
)
const NewRun = React.lazy(() => import("./pages/NewRun").then((m) => ({ default: m.NewRun })))
const RunDetail = React.lazy(() =>
  import("./pages/RunDetail").then((m) => ({ default: m.RunDetail })),
)
const CandidateDetail = React.lazy(() =>
  import("./pages/CandidateDetail").then((m) => ({ default: m.CandidateDetail })),
)
const DossierListingPage = React.lazy(() =>
  import("./pages/DossierListing").then((m) => ({ default: m.DossierListingPage })),
)
const Outbox = React.lazy(() => import("./pages/Outbox").then((m) => ({ default: m.Outbox })))
const OutboxDraftPage = React.lazy(() =>
  import("./pages/OutboxDraftPage").then((m) => ({ default: m.OutboxDraftPage })),
)
const ApplicationDetailPage = React.lazy(() =>
  import("./pages/ApplicationDetailPage").then((m) => ({ default: m.ApplicationDetailPage })),
)
const Schools = React.lazy(() =>
  import("./pages/Schools").then((m) => ({ default: m.Schools })),
)
const Professors = React.lazy(() =>
  import("./pages/Professors").then((m) => ({ default: m.Professors })),
)
const SchoolDetail = React.lazy(() =>
  import("./pages/SchoolDetail").then((m) => ({ default: m.SchoolDetail })),
)
const Documents = React.lazy(() => import("./pages/Documents").then((m) => ({ default: m.Documents })))
const CvRedirect = React.lazy(() => import("./pages/Documents").then((m) => ({ default: m.CvRedirect })))
const Login = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.Login })))
const AgentSettings = React.lazy(() =>
  import("./pages/AgentSettings").then((m) => ({ default: m.AgentSettings })),
)
const PlanPicker = React.lazy(() => import("./pages/Plans").then((m) => ({ default: m.PlanPicker })))
const Checkout = React.lazy(() => import("./pages/Plans").then((m) => ({ default: m.Checkout })))
const Register = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.Register })))
const Privacy = React.lazy(() => import("./pages/Legal").then((m) => ({ default: m.Privacy })))
const Terms = React.lazy(() => import("./pages/Legal").then((m) => ({ default: m.Terms })))
const ForgotPassword = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.ForgotPassword })))
const ResetPassword = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.ResetPassword })))
const OAuthCallback = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.OAuthCallback })))
const VerifyEmail = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.VerifyEmail })))
const UnsubscribeEmail = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.UnsubscribeEmail })))

/**
 * Login gate for app routes. Anonymous visitors get /login?next=; the boot
 * refresh settles first so a restored session never flashes the login page.
 */
const PLAN_STEP_PATHS = ["/plans", "/billing/checkout"]

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth()
  const location = useLocation()
  if (!ready) return <LoadingScreen />
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  // Onboarding's plan step: pick a plan before anything else, then continue.
  if (user.needs_plan && !PLAN_STEP_PATHS.includes(location.pathname)) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/plans?next=${next}`} replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <React.Suspense fallback={<LoadingScreen />}>
        {/* Last-resort boundary; pages also have their own in the shell. */}
        <ErrorBoundary>
        <Routes>
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route path="runs/:runId" element={<RunDetail />} />

            <Route path="runs/:runId/programmes/:programId" element={<ProgramProfessors />} />

            {/* Retired route: candidate pages live at /dossier/:candidateId. */}
            <Route path="runs/:runId/candidates/:candidateId" element={<CandidateRedirect />} />

            {/* Listings preview via ?preview=; /:id paths are full pages. */}
            <Route path="dossier" element={<DossierListingPage />} />
            <Route path="dossier/:candidateId" element={<CandidateDetail />} />
            <Route path="professors" element={<Professors />} />
            <Route path="professors/:professorId" element={<ProfessorDetailPage />} />

            <Route path="outbox" element={<Outbox />} />
            <Route path="outbox/:draftId" element={<OutboxDraftPage />} />

            <Route path="applications" element={<Applications />} />
            <Route path="applications/:appId" element={<ApplicationDetailPage />} />

            <Route path="schools" element={<Schools />} />
            <Route path="schools/:schoolId" element={<SchoolDetail />} />

            <Route path="new" element={<NewRun />} />

            <Route path="chat" element={<GradisPage />} />
            <Route path="chat/:conversationId" element={<GradisPage />} />

            <Route path="settings/agents" element={<AgentSettings />} />
            {/* Models live in the settings dialog; old links open it there. */}
            <Route path="settings/models" element={<Navigate to="/?settings=models" replace />} />

            <Route path="*" element={<NotFound />} />
          </Route>

          {/* Public "/": the app for signed-in users, the site for visitors. */}
          <Route index element={<Home />} />
          <Route path="login" element={<Login />} />
          <Route path="register" element={<Register />} />
          <Route path="privacy" element={<Privacy />} />
          <Route path="terms" element={<Terms />} />
          <Route path="forgot-password" element={<ForgotPassword />} />
          <Route path="reset-password" element={<ResetPassword />} />
          <Route path="verify-email" element={<VerifyEmail />} />
          <Route path="notifications/unsubscribe" element={<UnsubscribeEmail />} />
          <Route path="auth/callback/:provider" element={<OAuthCallback />} />

          {/* Outside the shell. */}
          <Route path="plans" element={<RequireAuth><PlanPicker /></RequireAuth>} />
          <Route path="billing/checkout" element={<RequireAuth><Checkout /></RequireAuth>} />

          {/* Outside the shell, with their own toolbar and list. */}
          <Route path="documents" element={<RequireAuth><Documents /></RequireAuth>} />
          <Route path="documents/:documentId" element={<RequireAuth><Documents /></RequireAuth>} />
          <Route path="cv" element={<CvRedirect />} />
          <Route path="cv/:documentId" element={<CvRedirect />} />
        </Routes>
        </ErrorBoundary>
      </React.Suspense>
    </BrowserRouter>
  )
}

/** "/": signed-in users go to the new-run flow; everyone else goes to the site. */
function Home() {
  const { user, ready } = useAuth()
  if (!ready) return <LoadingScreen />
  if (user) return <Navigate to="/new" replace />
  return <SiteRedirect />
}

/**
 * Sends anonymous visitors to the marketing site. Without a configured site
 * (local dev) it offers the app itself instead of a blank page.
 */
function SiteRedirect() {
  React.useEffect(() => {
    if (SITE_URL) window.location.replace(SITE_URL)
  }, [])
  if (SITE_URL) return <LoadingScreen />
  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-6 px-4 text-center">
      <AppLogo className="size-10" />
      <h1 className="type-page-title">Graduator</h1>
      <p className="type-meta">
        A research assistant for graduate school applications. Sign in, or create an account to start a run.
      </p>
      <div className="flex gap-3">
        <Link to="/register" className={buttonVariants()}>Create account</Link>
        <Link to="/login" className={buttonVariants({ variant: "outline" })}>Sign in</Link>
      </div>
    </div>
  )
}

function CandidateRedirect() {
  const { candidateId } = useParams<{ candidateId: string }>()
  return <Navigate to={`/dossier/${candidateId}`} replace />
}

function NotFound() {
  return (
    <ErrorState
      mascot="not-found"
      title="Page not found"
      description="The link you followed doesn't exist. Gradis checked twice."
      action={<Link to="/new" className={buttonVariants({ size: "sm" })}>Start a run</Link>}
    />
  )
}

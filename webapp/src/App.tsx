import * as React from "react"
import { BrowserRouter, Link, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom"
import { ErrorState } from "./components/feedback/EmptyState"
import { ErrorBoundary } from "./components/feedback/ErrorBoundary"
import { LoadingScreen } from "./components/feedback/LoadingScreen"
import { AppLogo } from "./components/layout/AppLogo"
import { buttonVariants } from "./components/ui/button"
import { useAuth } from "./lib/auth"

const Shell = React.lazy(() => import("./components/layout/Shell").then((m) => ({ default: m.Shell })))
const Opportunities = React.lazy(() => import("./pages/Opportunities").then((m) => ({ default: m.Opportunities })))
const Applications = React.lazy(() => import("./pages/Applications").then((m) => ({ default: m.Applications })))
const Todos = React.lazy(() => import("./pages/Todos").then((m) => ({ default: m.Todos })))
const Scans = React.lazy(() => import("./pages/Scans").then((m) => ({ default: m.Scans })))
const ScanDetail = React.lazy(() => import("./pages/Scans").then((m) => ({ default: m.ScanDetail })))
const Settings = React.lazy(() => import("./pages/Settings").then((m) => ({ default: m.Settings })))
const Login = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.Login })))
const Register = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.Register })))
const ForgotPassword = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.ForgotPassword })))
const ResetPassword = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.ResetPassword })))
const OAuthCallback = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.OAuthCallback })))
const VerifyEmail = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.VerifyEmail })))
const UnsubscribeEmail = React.lazy(() => import("./pages/Auth").then((m) => ({ default: m.UnsubscribeEmail })))
const Privacy = React.lazy(() => import("./pages/Legal").then((m) => ({ default: m.Privacy })))
const Terms = React.lazy(() => import("./pages/Legal").then((m) => ({ default: m.Terms })))

/** Anonymous visitors go to sign-in; the boot refresh settles first so a session never flashes it. */
function RequireAuth() {
  const { user, ready } = useAuth()
  const location = useLocation()
  if (!ready) return <LoadingScreen />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
  return <Shell />
}

/** The catalogue is public: the app shell when signed in, a light frame otherwise. */
function MaybeShell() {
  const { user, ready } = useAuth()
  if (!ready) return <LoadingScreen />
  if (user) return <Shell />
  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-10 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1080px] items-center gap-3 px-4 py-3 sm:px-6">
          <Link to="/opportunities" className="flex items-center gap-2">
            <AppLogo className="size-7" />
            <span className="text-[17px] font-semibold tracking-[-0.02em] text-label">Blesser</span>
          </Link>
          <nav className="ml-auto flex gap-2">
            <Link to="/login" className={buttonVariants({ size: "sm", variant: "ghost" })}>Sign in</Link>
            <Link to="/register" className={buttonVariants({ size: "sm" })}>Create account</Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1080px] px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}

function NotFound() {
  return (
    <ErrorState
      title="Page not found"
      description="The link you followed doesn't exist."
      action={<Link to="/opportunities" className={buttonVariants({ size: "sm" })}>Browse opportunities</Link>}
    />
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <React.Suspense fallback={<LoadingScreen />}>
        <ErrorBoundary>
          <Routes>
            <Route index element={<Navigate to="/opportunities" replace />} />
            <Route element={<MaybeShell />}>
              <Route path="opportunities" element={<Opportunities />} />
            </Route>
            <Route element={<RequireAuth />}>
              <Route path="applications" element={<Applications />} />
              <Route path="todos" element={<Todos />} />
              <Route path="scans" element={<Scans />} />
              <Route path="scans/:scanId" element={<ScanDetail />} />
              <Route path="settings" element={<Settings />} />
              <Route path="*" element={<NotFound />} />
            </Route>
            <Route path="login" element={<Login />} />
            <Route path="register" element={<Register />} />
            <Route path="forgot-password" element={<ForgotPassword />} />
            <Route path="reset-password" element={<ResetPassword />} />
            <Route path="verify-email" element={<VerifyEmail />} />
            <Route path="notifications/unsubscribe" element={<UnsubscribeEmail />} />
            <Route path="auth/callback/:provider" element={<OAuthCallback />} />
            <Route path="privacy" element={<Privacy />} />
            <Route path="terms" element={<Terms />} />
          </Routes>
        </ErrorBoundary>
      </React.Suspense>
    </BrowserRouter>
  )
}

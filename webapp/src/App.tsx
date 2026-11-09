import * as React from "react"
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom"
import { EmptyState } from "./components/feedback/EmptyState"
import { ErrorBoundary } from "./components/feedback/ErrorBoundary"
import { LoadingScreen } from "./components/feedback/LoadingScreen"
import { buttonVariants } from "@blesser/ui"
import { useAuth } from "./lib/auth"
import { SITE_URL } from "./lib/site"
import notFoundArt from "@blesser/ui/illustrations/spot-not-found.webp"

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

/** Signed-out visitors at "/" belong on the public site (or sign-in when none is configured). */
function Home() {
  const { user, ready } = useAuth()
  const leave = ready && !user && SITE_URL !== null
  React.useEffect(() => {
    if (leave && SITE_URL) window.location.replace(SITE_URL)
  }, [leave])
  if (!ready || leave) return <LoadingScreen />
  return <Navigate to={user ? "/opportunities" : "/login"} replace />
}

function NotFound() {
  return (
    <EmptyState
      illustration={notFoundArt}
      title="Page not found"
      description="That link didn't open. Check the address, or head back to the opportunities."
      action={<Link to="/opportunities" className={buttonVariants({ size: "sm", variant: "primary" })}>Browse opportunities</Link>}
    />
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <React.Suspense fallback={<LoadingScreen />}>
        <ErrorBoundary>
          <Routes>
            <Route index element={<Home />} />
            <Route element={<RequireAuth />}>
              <Route path="opportunities" element={<Opportunities />} />
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

import { Component, type ReactNode } from "react";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
} from "react-router-dom";
import {
  ClipboardCheck,
  Rows3,
  Layers,
  Radar,
  Rss,
  Flag,
  Users,
  History,
  Settings,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import { Button, Chip, EmptyState, Logo, Wordmark } from "@blesser/ui";
import { toast } from "sonner";
import { Protected, useAuth } from "./lib/auth";
import * as api from "./lib/api";
import SignIn from "./pages/SignIn";
import Opportunities from "./pages/Opportunities";
import Curation from "./pages/Curation";
import Scans from "./pages/Scans";
import Reports from "./pages/Reports";
import Sources from "./pages/Sources";
import People from "./pages/People";
import Audit from "./pages/Audit";
import SettingsPage from "./pages/Settings";

const navigation: {
  path: string;
  label: string;
  icon: LucideIcon;
  admin?: boolean;
}[] = [
  { path: "/review", label: "Review queue", icon: ClipboardCheck },
  { path: "/opportunities", label: "Opportunities", icon: Rows3 },
  { path: "/curation", label: "Curation", icon: Layers },
  { path: "/scans", label: "Scans", icon: Radar },
  { path: "/sources", label: "Sources", icon: Rss },
  { path: "/reports", label: "Reports", icon: Flag },
  { path: "/people", label: "People", icon: Users, admin: true },
  { path: "/audit", label: "Audit log", icon: History, admin: true },
  { path: "/settings", label: "Settings", icon: Settings, admin: true },
];
function Shell() {
  const { user } = useAuth();
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar">
        <NavLink to="/review" className="wordmark">
          <Logo title="" />
          <span>
            <Wordmark className="block" />
            <span className="wordmark-sub">Admin console</span>
          </span>
        </NavLink>
        <nav aria-label="Main navigation">
          {navigation
            .filter((item) => !item.admin || user?.role === "admin")
            .map(({ path, label, icon: Icon }) => (
              <NavLink
                key={path}
                to={path}
                className={({ isActive }) =>
                  `nav-link ${isActive ? "active" : ""}`
                }
              >
                <Icon size={18} strokeWidth={1.7} />
                {label}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-user">
          <Chip tone="forest">
            {user?.role === "admin" ? "Admin" : "Editor"}
          </Chip>
          <p>{user?.display_name || user?.email}</p>
          <Button
            size="sm"
            variant="quiet"
            icon={<LogOut />}
            onClick={() => {
              void api
                .logout()
                .catch((error: unknown) =>
                  toast.error(
                    `Signed out on this device. ${api.errorMessage(error)}`,
                  ),
                );
            }}
          >
            Sign out
          </Button>
        </div>
      </aside>
      <main id="main" className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <EmptyState
        error
        title="This view could not be displayed"
        description="Reload the workspace to try again."
        action={
          <Button onClick={() => window.location.reload()}>
            Reload workspace
          </Button>
        }
      />
    ) : (
      this.props.children
    );
  }
}
export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/sign-in" element={<SignIn />} />
          <Route
            element={
              <Protected>
                <Shell />
              </Protected>
            }
          >
            <Route index element={<Navigate to="/review" replace />} />
            <Route path="review" element={<Opportunities review />} />
            <Route path="opportunities" element={<Opportunities />} />
            <Route path="curation" element={<Curation />} />
            <Route path="scans" element={<Scans />} />
            <Route path="sources" element={<Sources />} />
            <Route path="reports" element={<Reports />} />
            <Route
              path="people"
              element={
                <Protected adminOnly>
                  <People />
                </Protected>
              }
            />
            <Route
              path="audit"
              element={
                <Protected adminOnly>
                  <Audit />
                </Protected>
              }
            />
            <Route
              path="settings"
              element={
                <Protected adminOnly>
                  <SettingsPage />
                </Protected>
              }
            />
            <Route
              path="*"
              element={
                <EmptyState
                  title="This page is not here"
                  action={<NavLink to="/review">Open review queue</NavLink>}
                />
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

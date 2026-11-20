import { Component, useEffect, useState, type ReactNode } from "react";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
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
  Menu,
  X,
  type LucideIcon,
} from "lucide-react";
import { Button, EmptyState, Logo, Wordmark } from "@blesser/ui";
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
  group: string;
  admin?: boolean;
  items: { path: string; label: string; icon: LucideIcon }[];
}[] = [
  {
    group: "Editorial",
    items: [
      { path: "/review", label: "Review queue", icon: ClipboardCheck },
      { path: "/opportunities", label: "Opportunities", icon: Rows3 },
      { path: "/curation", label: "Curation", icon: Layers },
      { path: "/scans", label: "Scans", icon: Radar },
      { path: "/sources", label: "Sources", icon: Rss },
      { path: "/reports", label: "Reports", icon: Flag },
    ],
  },
  {
    group: "Manage",
    admin: true,
    items: [
      { path: "/people", label: "People", icon: Users },
      { path: "/audit", label: "Audit log", icon: History },
      { path: "/settings", label: "Settings", icon: Settings },
    ],
  },
];
const initials = (name: string) =>
  name
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
function Shell() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menuOpen]);
  const name = user?.display_name || user?.email || "";
  const brand = (
    <NavLink to="/review" className="wordmark" aria-label="Blesser admin home">
      <Logo title="" />
      <Wordmark />
    </NavLink>
  );
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="mobile-bar">
        {brand}
        <Button
          variant="quiet"
          icon={<Menu />}
          aria-label="Open navigation"
          aria-expanded={menuOpen}
          aria-controls="admin-sidebar"
          onClick={() => setMenuOpen(true)}
        />
      </header>
      <button
        type="button"
        className="sidebar-scrim"
        data-open={menuOpen}
        aria-hidden="true"
        tabIndex={-1}
        onClick={() => setMenuOpen(false)}
      />
      <aside id="admin-sidebar" className="sidebar" data-open={menuOpen}>
        <div className="sidebar-header">
          {brand}
          <Button
            className="sidebar-close min-[861px]:hidden"
            variant="quiet"
            size="sm"
            icon={<X />}
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          />
        </div>
        <nav aria-label="Main navigation">
          {navigation
            .filter((group) => !group.admin || user?.role === "admin")
            .map((group) => (
              <div key={group.group} className="nav-group">
                <p className="nav-group-label">{group.group}</p>
                {group.items.map(({ path, label, icon: Icon }) => (
                  <NavLink
                    key={path}
                    to={path}
                    className={({ isActive }) =>
                      `nav-link ${isActive ? "active" : ""}`
                    }
                  >
                    <Icon size={18} strokeWidth={1.75} />
                    {label}
                  </NavLink>
                ))}
              </div>
            ))}
        </nav>
        <div className="sidebar-user">
          <span className="avatar" aria-hidden="true">
            {initials(name)}
          </span>
          <span className="sidebar-user-text">
            <strong>{name}</strong>
            <span>{user?.role === "admin" ? "Admin" : "Editor"}</span>
          </span>
          <Button
            size="sm"
            variant="quiet"
            icon={<LogOut />}
            aria-label="Sign out"
            title="Sign out"
            onClick={() => {
              void api
                .logout()
                .catch((error: unknown) =>
                  toast.error(
                    `Signed out on this device. ${api.errorMessage(error)}`,
                  ),
                );
            }}
          />
        </div>
      </aside>
      <main id="main" className="main-content">
        <div key={pathname.split("/")[1]} className="page-enter">
          <Outlet />
        </div>
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

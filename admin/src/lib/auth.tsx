import {
  createContext,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Button, EmptyState } from "@blesser/ui";
import * as api from "./api";

const AuthContext = createContext<{
  user: api.StaffUser | null;
  ready: boolean;
}>({ user: null, ready: false });
export const useAuth = () => useContext(AuthContext);
export function AuthProvider({ children }: { children: ReactNode }) {
  const user = useSyncExternalStore(
    api.subscribeSession,
    api.getSessionUser,
    api.getSessionUser,
  );
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const client = useQueryClient();
  useEffect(() => {
    const identity = () => {
      const current = api.getSessionUser();
      return current
        ? `${current.id}:${current.role}:${current.disabled}`
        : null;
    };
    let previous = identity();
    return api.subscribeSession(() => {
      const next = identity();
      if (next !== previous) client.clear();
      previous = next;
    });
  }, [client]);
  useEffect(() => {
    let live = true;
    void api
      .refreshSession()
      .then(() => {
        if (live) {
          setReady(true);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!live) return;
        if (
          err instanceof api.ApiError &&
          (err.status === 401 || err.status === 403)
        )
          setReady(true);
        else setError(api.errorMessage(err));
      });
    return () => {
      live = false;
    };
  }, [attempt]);
  if (error && !ready)
    return (
      <EmptyState
        error
        title="Your session could not be restored"
        description={error}
        action={
          <>
            <Button
              onClick={() => {
                setError(null);
                setAttempt((n) => n + 1);
              }}
            >
              Try again
            </Button>
            <Button
              onClick={() => {
                api.clearSession();
                setError(null);
                setReady(true);
              }}
            >
              Sign in again
            </Button>
          </>
        }
      />
    );
  return <AuthContext value={{ user, ready }}>{children}</AuthContext>;
}
export function canAccess(
  user: api.StaffUser | null,
  adminOnly = false,
): boolean {
  return (
    !!user &&
    !user.disabled &&
    user.email_verified &&
    (user.role === "admin" || (!adminOnly && user.role === "editor"))
  );
}
export function RoleGuard({
  user,
  ready = true,
  adminOnly = false,
  children,
}: {
  user: api.StaffUser | null;
  ready?: boolean;
  adminOnly?: boolean;
  children: ReactNode;
}) {
  const location = useLocation();
  if (!ready)
    return (
      <p className="loading" role="status">
        Restoring your session…
      </p>
    );
  if (!user)
    return (
      <Navigate
        to="/sign-in"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  if (!canAccess(user, adminOnly))
    return (
      <EmptyState
        error
        title="An admin role is required"
        description="Open the review queue or ask an admin to update your access."
        action={<a href="/review">Open review queue</a>}
      />
    );
  return children;
}
export function Protected({
  adminOnly = false,
  children,
}: {
  adminOnly?: boolean;
  children: ReactNode;
}) {
  const { user, ready } = useAuth();
  return (
    <RoleGuard user={user} ready={ready} adminOnly={adminOnly}>
      {children}
    </RoleGuard>
  );
}

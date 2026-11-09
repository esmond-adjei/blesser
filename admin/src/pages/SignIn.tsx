import { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Button, Field, Logo } from "@blesser/ui";
import { useMutation } from "@tanstack/react-query";
import * as api from "../lib/api";
import { useAuth } from "../lib/auth";
import { MutationError } from "../components/shared";

export default function SignIn() {
  const { user, ready } = useAuth();
  const location = useLocation();
  const state: unknown = location.state;
  const destination =
    typeof state === "object" &&
    state !== null &&
    "from" in state &&
    typeof state.from === "string" &&
    state.from.startsWith("/") &&
    !state.from.startsWith("//") &&
    !state.from.startsWith("/sign-in")
      ? state.from
      : "/review";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const signIn = useMutation({ mutationFn: () => api.login(email, password) });
  if (!ready)
    return (
      <p className="loading" role="status">
        Restoring your session…
      </p>
    );
  if (user) return <Navigate to={destination} replace />;
  return (
    <main className="signin">
      <div className="signin-intro">
        <Logo className="size-12" />
        <p className="eyebrow">Blesser admin</p>
        <h1>
          Good finds.
          <br />
          Thoughtfully published.
        </h1>
        <p>
          Review discoveries, curate the catalogue and help the right
          opportunities reach people.
        </p>
      </div>
      <form
        className="signin-form"
        onSubmit={(e) => {
          e.preventDefault();
          signIn.mutate();
        }}
      >
        <h2>Sign in to your workspace</h2>
        <p className="text-ink-secondary">
          Use your verified editor or admin account.
        </p>
        <Field
          label="Email address"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <MutationError error={signIn.error} />
        <Button type="submit" variant="primary" disabled={signIn.isPending}>
          {signIn.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </main>
  );
}

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import favicon from "@blesser/ui/logos/blesser-mark.svg";
import { AuthProvider } from "./lib/auth";
import { ApiError } from "./lib/api";
import App from "./App";
import "./index.css";

// Follow the system theme; the tokens switch on [data-theme="dark"].
const dark = window.matchMedia("(prefers-color-scheme: dark)");
const applyTheme = () => {
  document.documentElement.dataset.theme = dark.matches ? "dark" : "light";
};
applyTheme();
dark.addEventListener("change", applyTheme);
const icon = document.getElementById("favicon");
if (icon instanceof HTMLLinkElement) icon.href = favicon;
const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, error) =>
        !(error instanceof ApiError && error.status < 500) && count < 1,
    },
  },
});
const root = document.getElementById("root");
if (!root) throw new Error("The workspace root is missing. Reload the page.");
createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <AuthProvider>
        <App />
      </AuthProvider>
      <Toaster
        position="bottom-right"
        theme="system"
        closeButton
        toastOptions={{
          style: {
            background: "var(--surface-raised)",
            color: "var(--ink)",
            border: 0,
            fontFamily: "var(--font-sans)",
          },
        }}
      />
    </QueryClientProvider>
  </StrictMode>,
);

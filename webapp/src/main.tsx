import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ApiError } from "./lib/api"
import { Toaster } from "sonner"
import "./index.css"
import App from "./App"
import { TooltipProvider } from "./components/ui/tooltip"
import { AuthProvider } from "./lib/auth"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retry transient server/network failures once; client errors won't change.
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 1,
      // Reuse the cache for 30s. Mutations invalidate explicitly and live views poll.
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider>
          <App />
        </TooltipProvider>
      </AuthProvider>
      <Toaster
        className="bg-transparent!"
        position="bottom-right"
        theme="system"
        toastOptions={{ style: { background: "var(--surface-raised)", color: "var(--label)", border: 0, borderRadius: "var(--radius-lg)", boxShadow: "var(--elevation-2)", font: "400 14px/20px var(--font-sans)" }, classNames: { success: "toast-success", error: "toast-error", warning: "toast-warning" } }}
        closeButton
      />
    </QueryClientProvider>
  </StrictMode>,
)

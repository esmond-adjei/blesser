import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ApiError } from "./lib/api"
import "./index.css"
import App from "./App"
import { TooltipProvider } from "./components/ui/tooltip"
import { AuthProvider } from "./lib/auth"
import { initTheme } from "./lib/theme"
import { AppToaster } from "./components/feedback/AppToaster"

initTheme()

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
      <AppToaster />
    </QueryClientProvider>
  </StrictMode>,
)


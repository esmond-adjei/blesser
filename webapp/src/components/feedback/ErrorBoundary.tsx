import * as React from "react"
import { RotateCw } from "lucide-react"
import { Button, cn } from "@blesser/ui"
import { ErrorState } from "./EmptyState"

/** `resetKey` (e.g. the route path) clears the error when the user moves on. */
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; resetKey?: string; compact?: boolean; className?: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack)
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className={cn("flex min-h-dvh w-full items-center justify-center p-4", this.props.className)}>
        <ErrorState
          className="w-full max-w-lg"
          title="This part of Blesser stopped working"
          description="Your data is safe. Try again, or reload the page if it keeps happening."
          action={
            <span className="flex flex-wrap justify-center gap-2">
              <Button size="sm" variant="primary" onClick={() => this.setState({ error: null })} icon={<RotateCw />}>
                Try again
              </Button>
              <Button size="sm" onClick={() => window.location.reload()}>
                Reload page
              </Button>
            </span>
          }
        />
      </div>
    )
  }
}

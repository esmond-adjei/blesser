import * as React from "react"
import { RotateCw } from "lucide-react"
import { Button } from "../ui/button"
import { ErrorState } from "./EmptyState"

/** `resetKey` (e.g. the route path) clears the error when the user moves on. */
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; resetKey?: string; compact?: boolean },
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
      <ErrorState
        mascot="error-gear"
        title="This part of Graduator hit a snag"
        description="Your data is safe. Try again, or reload the page if it keeps happening."
        action={
          <span className="flex flex-wrap justify-center gap-2">
            <Button size="sm" onClick={() => this.setState({ error: null })}>
              <RotateCw /> Try again
            </Button>
            <Button size="sm" variant="outline" onClick={() => window.location.reload()}>
              Reload page
            </Button>
          </span>
        }
      />
    )
  }
}

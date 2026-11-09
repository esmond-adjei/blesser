import { Toaster } from "sonner"
import { useTheme } from "../../lib/theme"

export function AppToaster() {
  return (
    <Toaster
      className="bg-transparent!"
      position="bottom-right"
      theme={useTheme().resolved}
      toastOptions={{ style: { background: "var(--surface-raised)", color: "var(--ink)", border: 0, borderRadius: "var(--radius-md)", boxShadow: "var(--elevation-2)", font: "400 14px/20px var(--font-sans)" }, classNames: { success: "toast-success", error: "toast-error", warning: "toast-warning" } }}
      closeButton
    />
  )
}

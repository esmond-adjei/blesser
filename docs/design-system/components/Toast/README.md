# Toast

A toast confirms that something just happened and leaves on its own.

In the app: Sonner's `toast()` (`<Toaster>` in `main.tsx`): bottom-right, follows the system theme, with a close button. Each toast is `surface-raised`, `radius-lg`, `elevation-2`, 14/20 text, no border; the icon takes the tone (`positive` for success, `critical` for error, `caution` for warning).

Markup here: `.g-toast` (`role="status"`, or `role="alert"` with `.g-toast--critical`; `.g-toast--caution` for warnings) with a 20px icon, a `.g-toast__title` in past tense ("Draft approved"), an optional second line, and a close button.

Don't: toast things the person can already see change, or use a toast for an error that needs action (use a Banner).

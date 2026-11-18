import { EmptyState, buttonVariants } from "@blesser/ui"

type Action = { href: string; label: string; primary?: boolean }

/** EmptyState with link actions; Astro markup can't be passed as a React prop, so the links are built here. */
export function LinkEmptyState({
  title,
  description,
  error,
  actions = [],
  className,
}: {
  title: string
  description?: string
  error?: boolean
  actions?: Action[]
  className?: string
}) {
  return (
    <EmptyState
      title={title}
      description={description}
      error={error}
      className={className}
      action={
        actions.length ? (
          <>
            {actions.map((a) => (
              <a key={a.href + a.label} href={a.href} className={buttonVariants({ variant: a.primary ? "primary" : "secondary" })}>
                {a.label}
              </a>
            ))}
          </>
        ) : null
      }
    />
  )
}

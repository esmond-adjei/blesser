import { useEffect, useRef, type ReactNode } from "react";
import { Button, Chip, EmptyState, type ChipTone } from "@blesser/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { X } from "lucide-react";
import { errorMessage, type Status } from "../lib/api";

export const statusLabels: Record<Status, string> = {
  draft: "Draft",
  in_review: "In review",
  published: "Published",
  archived: "Archived",
  hidden: "Hidden",
};
const tones: Record<Status, ChipTone> = {
  draft: "neutral",
  in_review: "sun",
  published: "forest",
  archived: "neutral",
  hidden: "critical",
};
export const StatusChip = ({ status }: { status: Status }) => (
  <Chip tone={tones[status]}>{statusLabels[status]}</Chip>
);
export const formatDate = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("en-GH", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Africa/Accra",
      }).format(new Date(value))
    : "Not recorded";
export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        <p className="text-ink-secondary">{description}</p>
      </div>
      {action}
    </header>
  );
}
/** One pressed option in a sunk well, like the member app's view switcher. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  aside,
}: {
  label: string;
  value: T;
  options: readonly (readonly [T, string])[];
  onChange: (value: T) => void;
  aside?: ReactNode;
}) {
  return (
    <div className="tabs">
      <div className="segmented" role="group" aria-label={label}>
        {options.map(([key, text]) => (
          <button
            key={key}
            type="button"
            aria-pressed={value === key}
            onClick={() => onChange(key)}
          >
            {text}
          </button>
        ))}
      </div>
      {aside}
    </div>
  );
}
export function QueryState({
  query,
  empty,
  children,
}: {
  query: {
    isPending: boolean;
    isError: boolean;
    error: unknown;
    refetch: () => unknown;
  };
  empty: boolean;
  children: ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="loading" role="status">
        Loading…
      </div>
    );
  if (query.isError)
    return (
      <EmptyState
        error
        title="This view could not be loaded"
        description={errorMessage(query.error)}
        action={
          <Button
            onClick={() => {
              void query.refetch();
            }}
          >
            Try again
          </Button>
        }
      />
    );
  if (empty)
    return (
      <EmptyState
        title="Nothing here yet"
        description="Try another filter or check back after the next scan."
      />
    );
  return children;
}
export function useAction<T, R>(
  fn: (value: T) => Promise<R>,
  message: string,
  onSuccess?: (result: R) => void,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result) => {
      await client.invalidateQueries();
      toast.success(message);
      onSuccess?.(result);
    },
    onError: (error) => {
      void client.invalidateQueries();
      toast.error(errorMessage(error));
    },
  });
}
export function MutationError({ error }: { error: unknown }) {
  return error ? (
    <p className="error" role="alert">
      {errorMessage(error)} Check the details and try again.
    </p>
  ) : null;
}
export function Confirm({
  title,
  description,
  label,
  busy,
  error,
  onConfirm,
  onCancel,
  danger = false,
}: {
  title: string;
  description: string;
  label: string;
  busy: boolean;
  error: unknown;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    confirmRef.current?.focus();
  }, []);
  return (
    <section className="confirmation" role="region" aria-label={title}>
      <h3>{title}</h3>
      <p>{description}</p>
      <MutationError error={error} />
      <div className="actions">
        <Button
          ref={confirmRef}
          variant={danger ? "danger" : "brand"}
          disabled={busy}
          onClick={onConfirm}
        >
          {busy ? "Saving…" : label}
        </Button>
        <Button disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
export function Panel({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    ref.current?.showModal();
    return () => {
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`side-panel ${wide ? "wide" : ""}`}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        close.current();
      }}
    >
      <header className="panel-header">
        <h2>{title}</h2>
        <Button
          variant="quiet"
          icon={<X />}
          aria-label="Close panel"
          onClick={onClose}
        />
      </header>
      <div className="panel-body">{children}</div>
    </dialog>
  );
}
export function Pagination({
  offset,
  limit,
  total,
  count,
  onChange,
}: {
  offset: number;
  limit: number;
  total?: number;
  count: number;
  onChange: (offset: number) => void;
}) {
  if (total === undefined && count < limit || total === 0) return null;

  return (
    <footer className="pagination">
      <span>
        {count ? `${offset + 1}–${offset + count}` : "0"}
        {total === undefined ? "" : ` of ${total}`}
      </span>
      <div className="actions">
        <Button
          size="sm"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </Button>
        <Button
          size="sm"
          disabled={
            total === undefined ? count < limit : offset + count >= total
          }
          onClick={() => onChange(offset + limit)}
        >
          Next
        </Button>
      </div>
    </footer>
  );
}
export function SafeLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  try {
    const url = new URL(href);
    if (url.protocol === "https:" || url.protocol === "http:")
      return (
        <a
          className="text-link underline underline-offset-4"
          href={href}
          target="_blank"
          rel="noreferrer"
        >
          {children} ↗
        </a>
      );
  } catch {
    return <span>{children}: link unavailable</span>;
  }
  return <span>{children}: link unavailable</span>;
}

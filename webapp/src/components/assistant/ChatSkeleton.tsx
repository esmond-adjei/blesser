import { Skeleton } from "../ui/shadcn/skeleton"

/** Placeholder turns shaped like a chat while it loads. */
export function ChatSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-col gap-6 px-4 py-6 sm:px-6" role="status" aria-label="Loading chat">
      {[0, 1].map((turn) => (
        <div key={turn} className="flex flex-col gap-5">
          <Skeleton className="h-11 w-3/5 self-end rounded-[20px_20px_6px_20px] bg-surface-sunk sm:w-2/5" />
          <div className="flex flex-col gap-2.5">
            <Skeleton className="mb-1 h-4 w-36 bg-surface-sunk" />
            <Skeleton className="h-3.5 w-full bg-surface-sunk" />
            <Skeleton className="h-3.5 w-11/12 bg-surface-sunk" />
            <Skeleton className="h-3.5 w-2/3 bg-surface-sunk" />
          </div>
        </div>
      ))}
    </div>
  )
}

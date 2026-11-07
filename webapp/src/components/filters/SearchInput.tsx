import { Search } from "lucide-react"
import { cn } from "../../lib/utils"

export function SearchInput({
  value,
  onChange,
  placeholder,
  className,
  inputClassName,
  autoFocus,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  inputClassName?: string
  autoFocus?: boolean
}) {
  return (
    <label className={cn("g-search", className)}>
      <Search aria-hidden className="size-4 shrink-0" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        autoFocus={autoFocus}
        className={cn("text-sm", inputClassName)}
      />
    </label>
  )
}

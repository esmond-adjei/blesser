import * as React from "react"

/** Inline name field: Enter or blur commits the text, Escape cancels with `null`. */
export function RenameInput({
  value,
  label,
  onDone,
  maxLength,
  selectOnFocus = false,
  fitContent = false,
  className,
}: {
  value: string
  label: string
  onDone: (next: string | null) => void
  maxLength?: number
  selectOnFocus?: boolean
  fitContent?: boolean
  className: string
}) {
  // `size` sizes it where field-sizing isn't supported (Firefox).
  const [chars, setChars] = React.useState(value.length)
  return (
    <input
      autoFocus
      defaultValue={value}
      aria-label={label}
      maxLength={maxLength}
      size={fitContent ? Math.max(chars, 4) : undefined}
      onChange={fitContent ? (e) => setChars(e.currentTarget.value.length) : undefined}
      onFocus={selectOnFocus ? (e) => e.currentTarget.select() : undefined}
      onBlur={(e) => onDone(e.currentTarget.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") onDone(e.currentTarget.value)
        else if (e.key === "Escape") onDone(null)
      }}
      className={fitContent ? `[field-sizing:content] min-w-16 ${className}` : className}
    />
  )
}

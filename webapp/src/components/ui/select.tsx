import * as React from "react"
import { cn } from "../../lib/utils"

/** Native select as the system's field; native keyboard support. */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  placeholder?: string
}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, placeholder, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        // The system's field, with a chevron so it reads as a choice.
        "g-select w-full cursor-pointer appearance-none bg-[length:16px] bg-[right_10px_center] bg-no-repeat pr-9 text-sm disabled:cursor-not-allowed disabled:opacity-50",
        "bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237d8899' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")]",
        !props.value && "text-label-tertiary",
        className,
      )}
      {...props}
    >
      {placeholder ? <option value="">{placeholder}</option> : null}
      {children}
    </select>
  ),
)
Select.displayName = "Select"

export { Select }

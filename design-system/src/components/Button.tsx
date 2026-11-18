import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../lib"

export const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-full border font-semibold whitespace-nowrap no-underline transition-[background-color,transform,box-shadow] duration-160 ease-out select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&_svg]:size-[18px] [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "border-transparent bg-sun text-on-sun hover:bg-sun-hover",
        brand: "border-transparent bg-forest text-on-forest hover:bg-forest-hover",
        secondary: "border-control-border bg-surface text-ink hover:bg-highlight",
        quiet: "border-transparent bg-transparent text-ink hover:bg-highlight",
        danger: "border-transparent bg-critical text-on-critical hover:bg-critical/90",
      },
      size: {
        sm: "h-control-sm px-3.5 text-[13px] leading-5",
        md: "h-control-md px-[18px] text-sm leading-5",
        lg: "h-control-lg px-6 text-base leading-6",
      },
      iconOnly: { true: "aspect-square px-0" },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  icon?: React.ReactNode
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, iconOnly, icon, type = "button", children, ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size, iconOnly: iconOnly ?? (!!icon && children == null) }), className)}
      {...props}
    >
      {icon}
      {children}
    </button>
  ),
)
Button.displayName = "Button"

/* eslint-disable react/only-export-components -- canonical shadcn/ui pattern: variants exported alongside the component */
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../lib/utils"

const buttonVariants = cva(
  "g-btn focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "g-btn--primary",
        secondary: "g-btn--secondary",
        outline: "g-btn--outline",
        ghost: "g-btn--plain",
        destructive: "g-btn--destructive",
        link: "g-btn--plain underline-offset-4 hover:underline",
      },
      size: {
        default: "",
        sm: "g-btn--sm",
        lg: "g-btn--lg",
        icon: "g-btn--icon",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
)
Button.displayName = "Button"

export { Button, buttonVariants }

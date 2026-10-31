import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "button-3d inline-flex h-11 cursor-pointer items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-45 active:brightness-90",
  {
    variants: {
      variant: {
        default: "button-primary bg-primary text-primary-foreground shadow-[0_12px_28px_rgba(91,100,220,0.22),inset_0_1px_0_rgba(255,255,255,0.24)] hover:bg-primary/90",
        secondary: "button-glass border border-white/10 bg-white/[0.065] text-secondary-foreground hover:border-primary/30 hover:bg-white/[0.1]",
        ghost: "button-ghost text-muted-foreground hover:bg-white/[0.06] hover:text-foreground",
        outline: "button-outline border border-white/[0.14] bg-white/[0.025] text-foreground hover:border-primary/35 hover:bg-white/[0.07]",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-11 px-3 text-xs",
        icon: "h-11 w-11 px-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };

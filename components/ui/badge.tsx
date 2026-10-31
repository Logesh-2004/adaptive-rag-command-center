import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-white/[0.12] bg-white/[0.045] px-2.5 py-1 text-xs font-medium text-muted-foreground shadow-[inset_0_1px_0_rgba(255,248,239,0.07)] backdrop-blur",
        className,
      )}
      {...props}
    />
  );
}

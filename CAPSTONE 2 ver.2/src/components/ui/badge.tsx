import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "destructive" | "outline";
}

const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant = "default", ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium",
        {
          "border-transparent bg-slate-100 text-slate-900": variant === "default",
          "border-slate-200 bg-slate-50 text-slate-700": variant === "secondary",
          "border-transparent bg-red-100 text-red-900": variant === "destructive",
          "border-slate-200 text-slate-700": variant === "outline",
        },
        className
      )}
      {...props}
    />
  )
);
Badge.displayName = "Badge";

export { Badge };

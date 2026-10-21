import type { HTMLAttributes } from "react";

import { cn } from "../../lib/cn";

type BadgeTone = "slate" | "blue" | "green" | "amber" | "red" | "cyan";

const toneClass: Record<BadgeTone, string> = {
  slate: "border-slate-200 bg-slate-50 text-slate-600",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  green: "border-green-200 bg-green-50 text-green-700",
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  red: "border-red-200 bg-red-50 text-red-700",
  cyan: "border-cyan-200 bg-cyan-50 text-cyan-700",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ className, tone = "slate", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold",
        toneClass[tone],
        className,
      )}
      {...props}
    />
  );
}

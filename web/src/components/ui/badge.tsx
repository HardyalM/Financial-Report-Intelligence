import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/cn";

/** Every badge carries an icon and text: status never relies on colour alone (UI.md 10). */
export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] font-medium leading-4 whitespace-nowrap [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      tone: {
        neutral: "border-line bg-surface-sunk text-ink-2",
        ok: "border-ok-line bg-ok-soft text-ok",
        single: "border-single-line bg-single-soft text-single",
        derived: "border-derived-line bg-derived-soft text-derived",
        confirmed: "border-confirmed-line bg-confirmed-soft text-confirmed",
        amber: "border-amber-line bg-amber-soft text-amber",
        review: "border-review-line bg-review-soft text-review",
        suggested: "border-suggested-line bg-suggested-soft text-suggested",
        missing: "border-missing-line bg-missing-soft text-missing",
        muted: "border-muted-line bg-muted-soft text-muted",
        accent: "border-transparent bg-accent-soft text-accent",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type Tone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

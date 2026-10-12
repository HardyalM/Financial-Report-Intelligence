import type * as React from "react";
import { cn } from "@/lib/cn";

/** The heading every report section opens with: an eyebrow, a title and one line of method. */
export function SectionHeading({
  id,
  eyebrow,
  title,
  description,
  aside,
  className,
}: {
  id?: string;
  eyebrow: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  aside?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-2", className)}>
      <div className="min-w-0 space-y-1">
        <p className="eyebrow">{eyebrow}</p>
        <h2 id={id} className="text-[19px] font-semibold tracking-[-0.02em] text-ink">
          {title}
        </h2>
        {description ? <p className="max-w-2xl text-[12.5px] leading-relaxed text-ink-3">{description}</p> : null}
      </div>
      {aside ? <div className="shrink-0">{aside}</div> : null}
    </div>
  );
}

"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

const SECTIONS = [
  { id: "figures", label: "Key figures" },
  { id: "ratios", label: "Ratios" },
  { id: "commentary", label: "Commentary" },
] as const;

/** In-page navigation under the app bar; the section in view is marked as current. */
export function SectionNav() {
  const [active, setActive] = React.useState<string>(SECTIONS[0].id);
  React.useEffect(() => {
    const targets = SECTIONS.map((s) => document.getElementById(s.id)).filter((e): e is HTMLElement => !!e);
    if (!targets.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-120px 0px -55% 0px" },
    );
    targets.forEach((t) => observer.observe(t));
    return () => observer.disconnect();
  }, []);
  return (
    <nav aria-label="Report sections" className="-mb-px flex gap-1 overflow-x-auto">
      {SECTIONS.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          aria-current={active === s.id ? "true" : undefined}
          className={cn(
            "relative whitespace-nowrap px-3 py-2.5 text-[13px] font-medium transition-colors",
            active === s.id ? "text-ink" : "text-ink-3 hover:text-ink-2",
          )}
        >
          {s.label}
          <span
            aria-hidden
            className={cn(
              "absolute inset-x-3 -bottom-px h-[2px] rounded-full bg-ink transition-opacity",
              active === s.id ? "opacity-100" : "opacity-0",
            )}
          />
        </a>
      ))}
    </nav>
  );
}

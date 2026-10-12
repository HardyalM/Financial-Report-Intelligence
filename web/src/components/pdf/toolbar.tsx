"use client";

import * as React from "react";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { shortcutLabel } from "./use-viewer-input";

/** A floating glass bar centred over the page; fades out when idle, back on hover or focus. */
export function GlassToolbar({
  idle,
  children,
  className,
  label = "Page controls",
}: {
  idle: boolean;
  children: React.ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <div
      role="toolbar"
      aria-label={label}
      data-idle={idle ? "true" : "false"}
      className={cn(
        "pdf-toolbar absolute left-1/2 z-20 flex -translate-x-1/2 items-center gap-0.5 rounded-2xl p-1",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function ToolDivider() {
  return <span aria-hidden className="mx-0.5 h-5 w-px bg-line-strong/70" />;
}

/** A toolbar button whose tooltip names the action and its shortcut (design-system Tooltip). */
export const ToolButton = React.forwardRef<
  HTMLButtonElement,
  {
    label: string;
    shortcut?: string;
    pressed?: boolean;
    children: React.ReactNode;
  } & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "children">
>(function ToolButton({ label, shortcut, pressed, children, className, ...props }, ref) {
  return (
    <Tooltip
      content={
        <span className="inline-flex items-center gap-2">
          {label}
          {shortcut ? <Kbd>{shortcutLabel(shortcut)}</Kbd> : null}
        </span>
      }
    >
      <button
        ref={ref}
        type="button"
        aria-label={label}
        aria-pressed={pressed}
        className={cn(
          "inline-flex size-8 items-center justify-center rounded-xl text-ink-2 transition-colors",
          "hover:bg-ink/[0.06] hover:text-ink active:scale-[0.96] disabled:pointer-events-none disabled:opacity-35",
          "[&_svg]:size-[17px]",
          pressed && "bg-ink/[0.08] text-ink",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    </Tooltip>
  );
});

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded-md border border-line bg-surface-sunk px-1.5 py-px font-sans text-[10.5px] font-medium text-ink-2">
      {children}
    </kbd>
  );
}

/** The page number, editable: type a page and press Enter to go there. */
export function PageJump({
  page,
  total,
  onJump,
  className,
}: {
  page: number;
  total: number | null;
  onJump: (page: number) => void;
  className?: string;
}) {
  const [draft, setDraft] = React.useState<string | null>(null);
  return (
    <form
      className={cn("flex items-center gap-1 px-1 text-[12px] text-ink-2", className)}
      onSubmit={(e) => {
        e.preventDefault();
        const n = Number(draft);
        if (Number.isInteger(n) && n >= 1 && (!total || n <= total)) onJump(n);
        setDraft(null);
      }}
    >
      <label className="sr-only" htmlFor="pdf-page-jump">
        Go to page
      </label>
      <input
        id="pdf-page-jump"
        inputMode="numeric"
        autoComplete="off"
        value={draft ?? String(page)}
        onFocus={(e) => {
          setDraft(String(page));
          requestAnimationFrame(() => e.target.select());
        }}
        onBlur={() => setDraft(null)}
        onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, ""))}
        onKeyDown={(e) => e.key === "Escape" && (e.currentTarget.blur(), setDraft(null))}
        className="num h-7 w-11 rounded-lg border border-transparent bg-ink/[0.05] text-center text-[12px] font-medium text-ink outline-none focus:border-accent/50 focus:bg-surface"
      />
      {total ? <span className="num text-ink-3">/ {total}</span> : null}
    </form>
  );
}

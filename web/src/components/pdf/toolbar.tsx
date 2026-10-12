"use client";

import { motion } from "motion/react";
import * as React from "react";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { spring, useSafeMotion } from "@/lib/motion";
import { shortcutLabel } from "./use-viewer-input";

/**
 * A floating glass bar centred over the page. It fades out when idle and returns on hover, focus
 * or activity, on a spring that starts from wherever it is, so moving in and out mid-fade never
 * jumps. Reduced motion: an opacity cross-fade only (MotionConfig).
 */
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
  const bar = React.useRef<HTMLDivElement>(null);
  const [engaged, setEngaged] = React.useState(false);
  const safe = useSafeMotion(); // reduced motion: these fade instead of moving
  // Shown while the pointer is over the page area it floats on, or focus is inside it.
  React.useEffect(() => {
    const stage = bar.current?.parentElement;
    if (!stage) return;
    const on = () => setEngaged(true);
    const off = () => setEngaged(stage.matches(":hover") || !!bar.current?.contains(document.activeElement));
    stage.addEventListener("pointerenter", on);
    stage.addEventListener("pointerleave", off);
    stage.addEventListener("focusin", on);
    const blur = () => requestAnimationFrame(off);
    stage.addEventListener("focusout", blur);
    return () => {
      stage.removeEventListener("pointerenter", on);
      stage.removeEventListener("pointerleave", off);
      stage.removeEventListener("focusin", on);
      stage.removeEventListener("focusout", blur);
    };
  }, []);
  const shown = !idle || engaged;
  return (
    <motion.div
      ref={bar}
      role="toolbar"
      aria-label={label}
      data-idle={shown ? "false" : "true"}
      initial={false}
      animate={safe({ opacity: shown ? 1 : 0, y: shown ? 0 : 8, scale: shown ? 1 : 0.98 })}
      transition={spring.snappy}
      style={{ x: "-50%" }}
      className={cn("pdf-toolbar absolute left-1/2 z-20 flex items-center gap-0.5 rounded-2xl p-1", className)}
    >
      {children}
    </motion.div>
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
    <kbd className="rounded-md border border-line bg-surface-sunk px-1.5 py-px font-sans text-[0.65625rem] font-medium text-ink-2">
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
      className={cn("flex items-center gap-1 px-1 text-[0.75rem] text-ink-2", className)}
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
        className="num h-7 w-11 rounded-lg border border-transparent bg-ink/[0.05] text-center text-[0.75rem] font-medium text-ink outline-none focus:border-accent/50 focus:bg-surface"
      />
      {total ? <span className="num text-ink-3">/ {total}</span> : null}
    </form>
  );
}

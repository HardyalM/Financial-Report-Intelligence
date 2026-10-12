"use client";

import * as React from "react";
import { AnimatePresence, motion } from "motion/react";
import { createPortal } from "react-dom";
import { spring, useSafeMotion } from "@/lib/motion";
import { cn } from "@/lib/cn";

export interface MenuItem {
  label: string;
  hint?: string;
  icon?: React.ReactNode;
  disabled?: boolean;
  run: () => void;
}

/**
 * A context menu in the design system's own surface, border, radius and shadow. Opens at the
 * pointer, stays on screen, closes on Escape, outside click, scroll or choice; arrow keys move.
 */
export function ContextMenu({
  at,
  items,
  onClose,
}: {
  at: { x: number; y: number } | null;
  items: MenuItem[];
  onClose: () => void;
}) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <AnimatePresence>{at ? <Menu key={`${at.x},${at.y}`} at={at} items={items} onClose={onClose} /> : null}</AnimatePresence>,
    document.body,
  );
}

function Menu({ at, items, onClose }: { at: { x: number; y: number }; items: MenuItem[]; onClose: () => void }) {
  const menu = React.useRef<HTMLDivElement>(null);
  const safe = useSafeMotion(); // reduced motion: these fade instead of moving
  const [pos, setPos] = React.useState<{ x: number; y: number } | null>(null);

  React.useLayoutEffect(() => {
    if (!menu.current) return;
    const { width, height } = menu.current.getBoundingClientRect();
    setPos({
      x: Math.min(at.x, window.innerWidth - width - 8),
      y: Math.min(at.y, window.innerHeight - height - 8),
    });
    menu.current.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
  }, [at]);

  React.useEffect(() => {
    const openedAt = performance.now();
    const close = (e: Event) => {
      if (e instanceof MouseEvent && menu.current?.contains(e.target as Node)) return;
      // A scroll in the first instant is the page settling (scroll restoration, a list
      // animating in), not the person scrolling away: native menus survive it too.
      if (e.type === "scroll" && performance.now() - openedAt < 150) return;
      onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const buttons = [...(menu.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
        const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
        buttons[(i + (e.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length]?.focus();
      }
    };
    window.addEventListener("pointerdown", close, true);
    window.addEventListener("scroll", close, true);
    window.addEventListener("blur", close);
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("pointerdown", close, true);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("blur", close);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [at, onClose]);

  // Grows from the point that was clicked, even when pushed back inside the window; leaves the
  // same way. Reduced motion: opacity only (MotionConfig).
  const origin = pos ? `${at.x - pos.x}px ${at.y - pos.y}px` : "0 0";
  return (
    <motion.div
      ref={menu}
      role="menu"
      initial={safe({ opacity: 0, scale: 0.96 })}
      animate={safe({ opacity: 1, scale: 1 })}
      exit={safe({ opacity: 0, scale: 0.96 })}
      transition={spring.snappy}
      className="fixed z-[70] min-w-48 rounded-xl border border-line bg-surface-raised p-1 text-[0.8125rem] text-ink shadow-[var(--shadow-pop)]"
      style={{ left: pos?.x ?? at.x, top: pos?.y ?? at.y, visibility: pos ? "visible" : "hidden", transformOrigin: origin }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {items.map((item) => (
        <button
          key={item.label}
          type="button"
          role="menuitem"
          disabled={item.disabled}
          onClick={() => {
            onClose();
            item.run();
          }}
          className={cn(
            "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left outline-none",
            "hover:bg-surface-sunk focus-visible:bg-surface-sunk disabled:opacity-40 [&_svg]:size-4 [&_svg]:text-ink-3",
          )}
        >
          {item.icon}
          <span className="flex-1 truncate">{item.label}</span>
          {item.hint ? <span className="text-[0.6875rem] text-ink-3">{item.hint}</span> : null}
        </button>
      ))}
    </motion.div>
  );
}

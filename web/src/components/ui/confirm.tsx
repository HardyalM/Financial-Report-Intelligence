"use client";

import { TriangleAlert } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import * as React from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { spring, useSafeMotion } from "@/lib/motion";

export interface ConfirmOptions {
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  /** "destructive" for an action that cannot be undone. */
  tone?: "default" | "destructive";
}

const ConfirmContext = React.createContext<(o: ConfirmOptions) => Promise<boolean>>(async () => false);

/**
 * A confirmation, used only for what cannot be undone (apple-design: confirm sparingly). It opens
 * on a spring, keeps focus inside, starts on Cancel so Enter never destroys by accident, and
 * Esc or a click outside cancels. `useConfirm()` returns a promise of the answer.
 */
export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [ask, setAsk] = React.useState<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null);
  const confirm = React.useCallback(
    (o: ConfirmOptions) => new Promise<boolean>((resolve) => setAsk({ ...o, resolve })),
    [],
  );
  const answer = (ok: boolean) => {
    ask?.resolve(ok);
    setAsk(null);
  };
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {typeof document !== "undefined"
        ? createPortal(<AnimatePresence>{ask ? <Dialog key="confirm" {...ask} onAnswer={answer} /> : null}</AnimatePresence>, document.body)
        : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return React.useContext(ConfirmContext);
}

function Dialog({ title, body, confirmLabel, tone = "default", onAnswer }: ConfirmOptions & { onAnswer: (ok: boolean) => void }) {
  const safe = useSafeMotion();
  const panel = React.useRef<HTMLDivElement>(null);
  const cancel = React.useRef<HTMLButtonElement>(null);
  const restore = React.useRef<HTMLElement | null>(null);
  React.useEffect(() => {
    restore.current = document.activeElement as HTMLElement | null;
    cancel.current?.focus();
    return () => restore.current?.focus?.({ preventScroll: true });
  }, []);
  // Topmost modal: its keys are handled at the window, before anything underneath sees them.
  const answer = React.useRef(onAnswer);
  answer.current = onAnswer;
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => onKeyDown(e);
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      answer.current(false);
    }
    if (e.key === "Tab") {
      // keep focus inside the dialog
      const items = [...(panel.current?.querySelectorAll<HTMLElement>("button") ?? [])];
      const i = items.indexOf(document.activeElement as HTMLElement);
      const next = items[(i + (e.shiftKey ? items.length - 1 : 1)) % items.length];
      e.preventDefault();
      next?.focus();
    }
  };
  return (
    <motion.div
      className="fixed inset-0 z-[85] flex items-center justify-center px-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={spring.snappy}
    >
      <div aria-hidden className="absolute inset-0 bg-[oklch(0.15_0.02_262/0.32)] backdrop-blur-[2px]" onClick={() => onAnswer(false)} />
      <motion.div
        ref={panel}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-body"
        data-testid="confirm-dialog"
        initial={safe({ opacity: 0, scale: 0.96, y: 6 })}
        animate={safe({ opacity: 1, scale: 1, y: 0 })}
        exit={safe({ opacity: 0, scale: 0.96, y: 6 })}
        transition={spring.modal}
        className="relative w-full max-w-[26rem] rounded-2xl border border-line bg-surface-raised p-5 shadow-[var(--shadow-pop)]"
      >
        <div className="flex gap-3.5">
          {tone === "destructive" ? (
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-missing-soft text-missing">
              <TriangleAlert aria-hidden className="size-[1.125rem]" />
            </span>
          ) : null}
          <div className="min-w-0 space-y-1.5">
            <h2 id="confirm-title" className="text-[1rem] font-semibold text-ink">
              {title}
            </h2>
            <div id="confirm-body" className="text-[0.8125rem] leading-relaxed text-ink-2">
              {body}
            </div>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            ref={cancel}
            type="button"
            onClick={() => onAnswer(false)}
            data-testid="confirm-cancel"
            className="h-9 rounded-lg border border-line-strong bg-surface px-3.5 text-[0.8125rem] font-medium text-ink hover:bg-surface-sunk"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onAnswer(true)}
            data-testid="confirm-ok"
            className={cn(
              "h-9 rounded-lg px-3.5 text-[0.8125rem] font-medium shadow-[var(--shadow-card)] hover:opacity-90",
              tone === "destructive" ? "bg-missing text-ink-inverse" : "bg-ink text-ink-inverse",
            )}
          >
            {confirmLabel}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

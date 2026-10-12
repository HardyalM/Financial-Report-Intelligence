"use client";

import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import * as React from "react";
import { cn } from "@/lib/cn";
import { spring } from "@/lib/motion";

type Tone = "info" | "ok" | "error";
interface Toast {
  id: number;
  title: string;
  body?: string;
  tone: Tone;
}

const ToastContext = React.createContext<(t: Omit<Toast, "id">) => void>(() => undefined);

/** Brief notices bottom-right: a decision saved, a refusal explained. Announced to screen readers. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const next = React.useRef(1);
  const show = React.useCallback((t: Omit<Toast, "id">) => {
    const id = next.current++;
    setToasts((list) => [...list.slice(-3), { ...t, id }]);
    window.setTimeout(() => setToasts((list) => list.filter((x) => x.id !== id)), t.tone === "error" ? 9000 : 4500);
  }, []);
  const Icon = { info: Info, ok: CircleCheck, error: CircleAlert };
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((t) => {
            const I = Icon[t.tone];
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, y: 12, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 24, transition: { duration: 0.16 } }}
                transition={spring.snappy}
                role={t.tone === "error" ? "alert" : "status"}
                data-testid="toast"
                className="pointer-events-auto flex items-start gap-3 rounded-xl border border-line bg-surface-raised p-3.5 shadow-[var(--shadow-pop)]"
              >
                <I aria-hidden className={cn("mt-0.5 size-4 shrink-0", t.tone === "error" ? "text-missing" : t.tone === "ok" ? "text-ok" : "text-accent")} />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-ink">{t.title}</p>
                  {t.body ? <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-2">{t.body}</p> : null}
                </div>
                <button
                  type="button"
                  aria-label="Dismiss"
                  onClick={() => setToasts((list) => list.filter((x) => x.id !== t.id))}
                  className="rounded-md p-0.5 text-ink-3 hover:bg-surface-sunk hover:text-ink"
                >
                  <X aria-hidden className="size-3.5" />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return React.useContext(ToastContext);
}

"use client";

import { useReportContext } from "@/components/report/context";

/** One code-rendered line (UI.md section 7). Written by the backend, never by a model. */
export function NumbersSnapshot() {
  const { commentary } = useReportContext();
  const snapshot = commentary?.validation?.snapshot;
  if (!snapshot?.rendered) return null;
  return (
    <div
      data-testid="numbers-snapshot"
      className="rounded-xl border border-line bg-surface px-4 py-3 text-[13px] leading-relaxed text-ink-2"
    >
      <span className="mr-2 text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">
        {snapshot.period_id}
      </span>
      <span className="num">{snapshot.rendered}</span>
    </div>
  );
}

"use client";

import { useReportContext } from "@/components/report/context";

/** One code-rendered line (UI.md section 7). Written by the backend, never by a model. */
export function NumbersSnapshot() {
  const { commentary, report } = useReportContext();
  const snapshot = commentary?.validation?.snapshot;
  if (!snapshot?.rendered) return null;
  // The snapshot is written in the corporate ratios' terms; for a bank they are not applicable
  // (shown on the cards), so the line would read "missing input" where the truth is "not
  // applicable". Hidden until the commentary writes a bank snapshot (follow-up in STATUS).
  if (report.document_type === "bank") return null;
  return (
    <div
      data-testid="numbers-snapshot"
      className="flex flex-col gap-1.5 rounded-2xl border border-line bg-surface px-5 py-3.5 text-[13px] leading-relaxed text-ink-2 shadow-[var(--shadow-card)] sm:flex-row sm:items-baseline sm:gap-4"
    >
      <span className="eyebrow shrink-0">
        Snapshot · <span className="num">{snapshot.period_id}</span>
      </span>
      <span className="num">{snapshot.rendered}</span>
    </div>
  );
}

"use client";

import * as React from "react";
import type { ReportData } from "@/lib/api";
import type { Period } from "@/lib/types";

/** What the evidence panel shows (UI.md section 6). */
export type Selection =
  | { kind: "figure"; item: string; period: string }
  | { kind: "input"; ratio: string; item: string; period: string }
  | null;

interface ReportContextValue extends ReportData {
  current: Period | null;
  prior: Period | null;
  selection: Selection;
  select: (s: Selection) => void;
  /** Scroll to a figures-table row and highlight it briefly (from a ratio card, UI.md K3). */
  focusRow: (item: string) => void;
}

const ReportContext = React.createContext<ReportContextValue | null>(null);

export function ReportProvider({ data, children }: { data: ReportData; children: React.ReactNode }) {
  const [selection, select] = React.useState<Selection>(null);
  const periods = data.report.pack?.periods ?? [];
  const focusRow = React.useCallback((item: string) => {
    const row = document.getElementById(`row-${item}`);
    if (!row) return;
    row.scrollIntoView({ behavior: "smooth", block: "center" });
    row.classList.remove("row-flash");
    void row.getBoundingClientRect();
    row.classList.add("row-flash");
    row.querySelector<HTMLElement>("[data-row-focus]")?.focus({ preventScroll: true });
  }, []);
  const value = React.useMemo(
    () => ({ ...data, current: periods[0] ?? null, prior: periods[1] ?? null, selection, select, focusRow }),
    [data, periods, selection, focusRow],
  );
  return <ReportContext.Provider value={value}>{children}</ReportContext.Provider>;
}

export function useReportContext(): ReportContextValue {
  const value = React.useContext(ReportContext);
  if (!value) throw new Error("useReportContext outside ReportProvider");
  return value;
}

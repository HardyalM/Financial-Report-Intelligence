"use client";

import { Quote } from "lucide-react";
import { PageChip } from "@/components/report/chips";
import { useReportContext } from "@/components/report/context";
import { Card } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import type { ReportedMetric } from "@/lib/types";

const ORDER = ["cet1_ratio", "cet1_ratio_pro_forma", "net_interest_margin"] as const;

/**
 * A bank's own CET1 ratio and net interest margin, as it states them (OQ-4 = B, SCHEMA 11).
 * Quoted verbatim with the page; never computed here and never an input to a ratio.
 */
export function ReportedMetrics() {
  const { reported, current, prior, select } = useReportContext();
  if (!reported.metrics.length && !reported.notes.length) return null;
  const at = (id: string, period: string | undefined) =>
    reported.metrics.find((m) => m.id === id && m.period_id === period) ?? null;
  const ids = ORDER.filter((id) => reported.metrics.some((m) => m.id === id));
  return (
    <section aria-labelledby="reported-heading" data-testid="reported-metrics">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="reported-heading" className="text-[15px] font-semibold tracking-[-0.01em]">
          Reported by the bank
        </h2>
        <p className="text-xs text-ink-3">Quoted from the report. Not computed here; never used in a ratio.</p>
      </div>
      <Card className="divide-y divide-line">
        {ids.map((id) => {
          const now = at(id, current?.id);
          const before = at(id, prior?.id);
          const any = (now ?? before)!;
          return (
            <div key={id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3" data-testid={`reported-${id}`}>
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-ink">{any.label}</p>
                <p className="text-[12px] text-ink-3">Printed as “{any.label_found}”</p>
              </div>
              <div className="flex items-center gap-4">
                <Figure metric={now} period={current?.id} onOpen={select} strong />
                <Figure metric={before} period={prior?.id} onOpen={select} />
              </div>
            </div>
          );
        })}
      </Card>
      {reported.notes.length ? (
        <ul className="mt-2 space-y-0.5 text-[12px] text-ink-3" data-testid="reported-notes">
          {reported.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function Figure({
  metric,
  period,
  onOpen,
  strong = false,
}: {
  metric: ReportedMetric | null;
  period: string | undefined;
  onOpen: ReturnType<typeof useReportContext>["select"];
  strong?: boolean;
}) {
  if (!metric) {
    return (
      <span className="num w-36 text-right text-[12.5px] text-ink-3">
        {period}: not stated
      </span>
    );
  }
  return (
    <span className="flex w-44 items-center justify-end gap-2">
      <Tooltip content={<><Quote aria-hidden className="mr-1 inline size-3" />{metric.quote}</>}>
        <span tabIndex={0} className={`num text-right ${strong ? "text-[14px] font-semibold text-ink" : "text-[12.5px] text-ink-2"}`}>
          <span className="mr-1.5 text-[11px] font-normal text-ink-3">{period}</span>
          {metric.value_text}
        </span>
      </Tooltip>
      <PageChip page={metric.page} label={metric.page_label} testId="reported-page-chip" onOpen={() => onOpen({ kind: "reported", metric })} />
    </span>
  );
}

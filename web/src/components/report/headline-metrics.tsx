"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight, UserPen } from "lucide-react";
import { useReportContext } from "@/components/report/context";
import { LOCKED } from "@/components/report/ratio-cards";
import { Tooltip } from "@/components/ui/tooltip";
import { formatFigure, formatPercentChange, formatRatio, formatRatioChange, shownDirection, unitLabel } from "@/lib/format";
import { itemLabel } from "@/lib/items";
import { cardInfo, cellInfo, ROW_STATE_LABEL, type RowState } from "@/lib/states";
import type { RatioName } from "@/lib/types";

type Metric = { kind: "item"; id: string } | { kind: "ratio"; id: RatioName };

const CORPORATE: Metric[] = [
  { kind: "item", id: "revenue" },
  { kind: "item", id: "operating_profit" },
  { kind: "ratio", id: "operating_margin" },
  { kind: "ratio", id: "roce" },
  { kind: "ratio", id: "current_ratio" },
  { kind: "ratio", id: "debt_to_equity" },
];

const BANK: Metric[] = [
  { kind: "item", id: "total_income" },
  { kind: "item", id: "profit_before_tax" },
  { kind: "ratio", id: "cost_to_income" },
  { kind: "ratio", id: "loan_to_deposit" },
  { kind: "item", id: "total_assets" },
  { kind: "item", id: "total_equity" },
];

/** Why a headline tile is empty, in two or three words (the full sentence is on the row). */
const SHORT_NULL: Partial<Record<RowState, string>> = {
  R6: "Needs review",
  R7: "Suggested, unconfirmed",
  R8: "Not found",
  R9: "Not applicable",
  R10: "Unit not confirmed",
};

/**
 * The headline strip: the figures a reader looks for first, as large tabular numbers with the
 * prior year and the change. Every value is the pack's or the ratio engine's, formatted by code;
 * a missing one stays empty and says why. Direction arrows are neutral (no green or red): a rise is
 * not a judgement.
 */
export function HeadlineMetrics() {
  const { report, current } = useReportContext();
  if (!report.pack || !current) return null;
  const metrics = report.document_type === "bank" ? BANK : CORPORATE;
  return (
    <section aria-label="Headline figures" data-testid="headline-metrics" className="mt-6">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line shadow-[var(--shadow-raised)] sm:grid-cols-3 xl:grid-cols-6">
        {metrics.map((m) => (
          <div key={m.id} className="bg-surface">
            {m.kind === "item" ? <ItemTile id={m.id} /> : <RatioTile name={m.id} />}
          </div>
        ))}
      </div>
    </section>
  );
}

function Tile({
  label,
  hint,
  value,
  unit,
  prior,
  change,
  note,
  manual = false,
  onOpen,
  testId,
}: {
  label: string;
  hint: string;
  value: string | null;
  unit?: string;
  prior: string | null;
  change: string | null;
  note?: string | null;
  manual?: boolean;
  onOpen: () => void;
  testId: string;
}) {
  const direction = change ? shownDirection(change) : 0;
  const Arrow = direction === 0 ? ArrowRight : direction > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <button
      type="button"
      onClick={onOpen}
      data-kpi={testId}
      className="group flex h-full w-full flex-col gap-2.5 px-4 py-4 text-left transition-colors hover:bg-surface-sunk/70 focus-visible:bg-surface-sunk/70 sm:px-5"
    >
      <span className="flex items-center gap-1.5">
        <Tooltip content={hint}>
          <span className="eyebrow truncate">{label}</span>
        </Tooltip>
        {manual ? (
          <Tooltip content="Uses a figure a person entered, forced or confirmed.">
            <UserPen aria-label="uses a manual figure" className="size-3 shrink-0 text-amber" />
          </Tooltip>
        ) : null}
      </span>
      {value === null ? (
        <span className="flex min-h-[30px] items-end gap-2">
          <span className="display-figure text-[1.625rem] text-ink-3" aria-label="not available">
            —
          </span>
          <span className="pb-0.5 text-[0.71875rem] font-medium text-ink-3">{note}</span>
        </span>
      ) : (
        <span className="flex min-h-[30px] items-baseline gap-1">
          <span className="display-figure text-[1.625rem] text-ink">{value}</span>
          {unit ? <span className="text-[0.75rem] font-medium text-ink-3">{unit}</span> : null}
        </span>
      )}
      <span className="num flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.71875rem] text-ink-3">
        {change ? (
          <span className="inline-flex items-center gap-0.5 font-medium text-ink-2">
            <Arrow aria-hidden className="size-3.5" />
            {change}
          </span>
        ) : null}
        {prior ? <span>{prior}</span> : null}
        {value !== null && note ? <span className="text-amber">{note}</span> : null}
      </span>
    </button>
  );
}

function ItemTile({ id }: { id: string }) {
  const { report, review, current, prior, select, focusRow } = useReportContext();
  const pack = report.pack!;
  const now = cellInfo(report, review?.items ?? [], id, current!.id);
  const before = prior ? cellInfo(report, review?.items ?? [], id, prior.id) : null;
  const change = prior
    ? (report.ratios?.changes.find((c) => c.to_period_id === current!.id && c.from_period_id === prior.id)?.items[id]
        ?.percent ?? null)
    : null;
  const v = now.value?.value ?? null;
  const p = before?.value?.value ?? null;
  return (
    <Tile
      testId={id}
      label={itemLabel(id)}
      hint={`${ROW_STATE_LABEL[now.state]}${now.value?.page ? ` · p.${now.value.page}` : ""}. Opens the source.`}
      value={v === null ? null : formatFigure(v)}
      unit={unitLabel(pack.currency, pack.unit_scale)}
      prior={prior ? `${prior.id} ${p === null ? "—" : formatFigure(p)}` : null}
      change={change === null ? null : formatPercentChange(change)}
      note={v === null ? (SHORT_NULL[now.state] ?? "Not available") : null}
      manual={now.state === "R4" || now.state === "R5"}
      onOpen={() => {
        focusRow(id);
        select({ kind: "figure", item: id, period: current!.id });
      }}
    />
  );
}

function RatioTile({ name }: { name: RatioName }) {
  const { report, current, prior, focusRatio } = useReportContext();
  const periods = report.ratios?.periods ?? [];
  const now = periods.find((x) => x.period_id === current?.id)?.ratios[name] ?? null;
  const before = periods.find((x) => x.period_id === prior?.id)?.ratios[name] ?? null;
  const info = cardInfo(report, now);
  const change = report.ratios?.changes.find((c) => c.to_period_id === current?.id && c.from_period_id === prior?.id)
    ?.ratios[name];
  const shown = (info.state === "K1" || info.state === "K2") && now?.value != null;
  const note =
    info.state === "K4"
      ? "Not applicable"
      : info.state === "K5"
        ? "Withheld"
        : info.state === "K3"
          ? "Missing input"
          : info.state === "K2"
            ? "Not meaningful"
            : null;
  return (
    <Tile
      testId={name}
      label={now?.label ?? LOCKED[name].label}
      hint={`${LOCKED[name].formula}. Opens the ratio card.`}
      value={shown ? formatRatio(now!.value!, now!.unit) : null}
      prior={prior && before ? `${prior.id} ${before.value != null ? formatRatio(before.value, before.unit) : "—"}` : null}
      change={shown && change?.value != null ? formatRatioChange(change.kind, change.value) : null}
      note={note}
      manual={info.manual}
      onOpen={() => focusRatio(name)}
    />
  );
}

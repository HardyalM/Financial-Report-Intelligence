"use client";

import { ArrowRight, Ban, ChevronRight, CircleHelp, FileQuestion, TriangleAlert, UserPen } from "lucide-react";
import * as React from "react";
import { PageChip } from "@/components/report/chips";
import { useReportContext } from "@/components/report/context";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { formatFigure, formatRatio, formatRatioChange, unitLabel } from "@/lib/format";
import { DEBT_COMPONENTS, itemLabel } from "@/lib/items";
import { cardInfo, cellInfo, missingPhrase } from "@/lib/states";
import type { Ratio, RatioName } from "@/lib/types";

/** Locked v1 definitions (CLAUDE.md). Shown on every card; the API's formula_text must agree. */
export const LOCKED: Record<RatioName, { label: string; formula: string }> = {
  operating_margin: { label: "Operating margin", formula: "Operating profit ÷ Revenue" },
  current_ratio: { label: "Current ratio", formula: "Current assets ÷ Current liabilities" },
  debt_to_equity: { label: "Debt-to-equity", formula: "Total debt ÷ Total equity" },
  roce: { label: "ROCE", formula: "Operating profit ÷ (Total assets − Current liabilities)" },
};
const ORDER: RatioName[] = ["operating_margin", "current_ratio", "debt_to_equity", "roce"];

export function RatioCards() {
  return (
    <section aria-labelledby="ratios-heading">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="ratios-heading" className="text-[15px] font-semibold tracking-[-0.01em]">
          Ratios
        </h2>
        <p className="text-xs text-ink-3">Computed in code from the figures above. Year-end balances.</p>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {ORDER.map((name) => (
          <RatioCard key={name} name={name} />
        ))}
      </div>
    </section>
  );
}

function RatioCard({ name }: { name: RatioName }) {
  const { report, current, prior } = useReportContext();
  const periods = report.ratios?.periods ?? [];
  const now = periods.find((p) => p.period_id === current?.id)?.ratios[name] ?? null;
  const before = periods.find((p) => p.period_id === prior?.id)?.ratios[name] ?? null;
  const info = cardInfo(report, now);
  const change = report.ratios?.changes.find(
    (c) => c.to_period_id === current?.id && c.from_period_id === prior?.id,
  )?.ratios[name];
  const locked = LOCKED[name];

  return (
    <Card data-testid={`ratio-card-state-${info.state}`} data-ratio={name} className="flex flex-col">
      <div className="flex items-start justify-between gap-3 px-5 pt-4">
        <div>
          <h3 className="text-[13px] font-semibold text-ink">{now?.label ?? locked.label}</h3>
          <p className="mt-0.5 text-[12px] text-ink-3" data-testid="ratio-formula">
            {now?.formula_text?.replace(" - ", " − ") ?? locked.formula}
          </p>
        </div>
        {info.manual ? (
          <Tooltip content="An input was entered, forced or confirmed by a person.">
            <Badge tone="amber" tabIndex={0} data-testid="ratio-card-state-K6">
              <UserPen aria-hidden />
              Uses a manual figure
            </Badge>
          </Tooltip>
        ) : null}
      </div>

      <div className="px-5 pb-1 pt-3">
        <CardValue name={name} ratio={now} prior={before} change={change ?? null} />
      </div>

      {info.state === "K1" || info.state === "K2" || info.state === "K3" ? (
        <Inputs ratio={now} name={name} />
      ) : null}
      {name === "debt_to_equity" && info.state !== "K4" && info.state !== "K5" ? <DebtSplit /> : null}
      {info.state === "K1" || info.state === "K2" ? (
        <p className="mt-auto border-t border-line px-5 py-2.5 text-[11.5px] leading-relaxed text-ink-3">
          Year-end balances; seasonal businesses may differ within the year.
        </p>
      ) : null}
    </Card>
  );

  function CardValue({
    name: n,
    ratio,
    prior: p,
    change: c,
  }: {
    name: RatioName;
    ratio: Ratio | null;
    prior: Ratio | null;
    change: { kind: "percentage_points" | "absolute"; value: number | null } | null;
  }) {
    if (info.state === "K5") {
      const unit = info.withheldFor === "unit";
      return (
        <div className="space-y-2 pb-3">
          <p className="flex items-center gap-1.5 text-[13px] font-medium text-ink-2">
            <CircleHelp aria-hidden className="size-4 text-ink-3" />
            {unit ? "Withheld until the unit is confirmed" : "Document type unclear: confirm to show ratios"}
          </p>
          <a
            href={unit ? "#banner-unit" : "#banner-document-type"}
            data-testid={unit ? "confirm-unit" : "confirm-document-type"}
            className="inline-flex items-center gap-1 text-[12.5px] font-medium text-accent hover:underline"
          >
            {unit ? "Why the unit matters" : "Confirm the document type"} <ArrowRight aria-hidden className="size-3.5" />
          </a>
        </div>
      );
    }
    if (info.state === "K4") {
      const explanation = ratio?.explanation ?? "Not applicable to this kind of report";
      const [headline, ...rest] = explanation.split(": ");
      return (
        <div className="space-y-1 pb-3">
          <p className="flex items-center gap-1.5 text-[13px] font-medium text-ink-2">
            <Ban aria-hidden className="size-4 text-ink-3" />
            {headline}
          </p>
          {rest.length ? <p className="text-[12.5px] leading-relaxed text-ink-3">{rest.join(": ")}</p> : null}
        </div>
      );
    }
    if (info.state === "K3" || !ratio || ratio.value === null) {
      return <MissingValue ratio={ratio} name={n} />;
    }
    return (
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pb-2">
        <span className="num text-[28px] font-semibold leading-none tracking-[-0.02em] text-ink" data-testid="ratio-value">
          {formatRatio(ratio.value, ratio.unit)}
        </span>
        {info.flag ? (
          <Badge tone="amber" data-testid="ratio-flag">
            <TriangleAlert aria-hidden />
            {info.flag}
          </Badge>
        ) : null}
        <span className="num flex basis-full flex-wrap gap-x-3 text-[12.5px] text-ink-3">
          {prior ? (
            <span data-testid="ratio-prior">
              {prior.id}: {p?.value != null ? formatRatio(p.value, p.unit) : "not available"}
            </span>
          ) : null}
          {c?.value != null ? (
            <span>
              Change{" "}
              <span className="font-medium text-ink-2" data-testid="ratio-change">
                {formatRatioChange(c.kind, c.value)}
              </span>
            </span>
          ) : null}
        </span>
      </div>
    );
  }
}

function MissingValue({ ratio, name }: { ratio: Ratio | null; name: RatioName }) {
  const { report, review, current, focusRow } = useReportContext();
  const missing = ratio?.missing_inputs ?? [];
  const zero = ratio?.reason === "division_by_zero";
  return (
    <div className="space-y-1.5 pb-3">
      <span className="num text-[28px] font-semibold leading-none text-ink-3" aria-label="not available">
        {"—"}
      </span>
      {zero ? (
        <p className="text-[12.5px] text-ink-2">Not computable: the denominator is zero.</p>
      ) : (
        <ul className="space-y-0.5">
          {missing.map((item) => {
            const state = current ? cellInfo(report, review?.items ?? [], item, current.id).state : "R8";
            return (
              <li key={item}>
                <button
                  type="button"
                  data-testid="ratio-missing-input"
                  data-item={item}
                  onClick={() => focusRow(item)}
                  className="inline-flex items-center gap-1 text-left text-[12.5px] font-medium text-accent hover:underline"
                >
                  <FileQuestion aria-hidden className="size-3.5" />
                  Needs {itemLabel(item).toLowerCase()}: {missingPhrase(state)}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <span className="sr-only">{name}</span>
    </div>
  );
}

function Inputs({ ratio, name }: { ratio: Ratio | null; name: RatioName }) {
  const { report, select } = useReportContext();
  if (!ratio) return null;
  const unit = unitLabel(report.pack?.currency, report.pack?.unit_scale);
  const entries = Object.values(ratio.inputs);
  return (
    <dl className="mx-5 mb-3 divide-y divide-line rounded-lg border border-line bg-surface-sunk/50 text-[12.5px]" data-testid="ratio-inputs">
      {entries.map((input) => (
        <div key={input.item} className="flex items-center justify-between gap-3 px-3 py-1.5">
          <dt className="flex items-center gap-1.5 text-ink-2">
            {itemLabel(input.item)}
            {input.badges.includes("derived") ? (
              <Badge tone="derived" className="px-1.5 text-[10.5px]">
                Derived
              </Badge>
            ) : null}
            {input.badges.some((b) => b.startsWith("manual")) ? (
              <Badge tone="amber" className="px-1.5 text-[10.5px]">
                <UserPen aria-hidden />
                {input.badges.includes("manual_unanchored") ? "Manual: not on page" : "Manual"}
              </Badge>
            ) : null}
          </dt>
          <dd className="flex items-center gap-2">
            <span className={cn("num", input.value == null ? "text-ink-3" : "text-ink")}>
              {input.value == null ? "—" : `${formatFigure(input.value)}`}
            </span>
            {input.page ? (
              <PageChip
                page={input.page}
                onOpen={() => select({ kind: "input", ratio: name, item: input.item, period: input.period_id })}
                testId="input-page-chip"
              />
            ) : null}
          </dd>
        </div>
      ))}
      <div className="px-3 py-1 text-right text-[10.5px] uppercase tracking-[0.06em] text-ink-3">{unit}</div>
    </dl>
  );
}

/** D/E only: total debt line by line, so a credit reader sees how much is leases (UI.md 5). */
function DebtSplit() {
  const { report, current, select } = useReportContext();
  const [open, setOpen] = React.useState(false);
  const pack = report.pack;
  if (!pack || !current) return null;
  const total = pack.items.total_debt?.values.find((v) => v.period_id === current.id);
  const parts = Object.keys(DEBT_COMPONENTS).map((id) => ({
    id,
    value: pack.items[id]?.values.find((v) => v.period_id === current.id) ?? null,
  }));
  const used = new Set(total?.derived_from?.map((d) => d.item) ?? []);
  return (
    <div className="mx-5 mb-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        data-testid="debt-split-toggle"
        className="inline-flex items-center gap-1 text-[12.5px] font-medium text-ink-2 hover:text-ink"
      >
        <ChevronRight aria-hidden className={cn("size-3.5 transition-transform", open && "rotate-90")} />
        Borrowings and lease liabilities
      </button>
      {open ? (
        <ul className="mt-1.5 space-y-1 text-[12.5px]" data-testid="debt-split">
          {parts.map(({ id, value }) => (
            <li key={id} className="flex items-center justify-between gap-2 pl-5">
              <span className={cn(used.has(id) ? "text-ink-2" : "text-ink-3")}>{DEBT_COMPONENTS[id]}</span>
              <span className="flex items-center gap-2">
                <span className="num">{value?.value != null ? formatFigure(value.value) : "—"}</span>
                {value?.page ? (
                  <PageChip
                    page={value.page}
                    label={value.page_label}
                    onOpen={() => select({ kind: "figure", item: id, period: current.id })}
                  />
                ) : null}
              </span>
            </li>
          ))}
          {total?.value == null ? (
            <li className="pl-5 text-ink-3">Total debt is not available for this period.</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}

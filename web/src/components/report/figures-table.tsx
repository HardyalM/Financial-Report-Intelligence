"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight, ChevronRight, Lock } from "lucide-react";
import * as React from "react";
import { CodeHint, NoteChip, PageChip, StateBadge } from "@/components/report/chips";
import { useReportContext } from "@/components/report/context";
import { Card } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { checkSentence, DECISION_SENTENCES, warningSentence } from "@/lib/copy";
import { formatFigure, formatPercentChange, pageRange, shownDirection, unitLabel } from "@/lib/format";
import {
  DEBT_COMPONENTS,
  GROUP_TITLES,
  ITEMS,
  type ItemDef,
  itemLabel,
  orderedItems,
  STATEMENT_NAMES,
} from "@/lib/items";
import { type CellInfo, cellInfo, type RowState } from "@/lib/states";
import type { DerivedComponent, PackWarning, Period } from "@/lib/types";

const NOTABLE: RowState[] = ["R3", "R4", "R5", "R6", "R7", "R8"];

export function FiguresTable() {
  const { report, current, prior } = useReportContext();
  const pack = report.pack;
  if (!pack || !current) {
    return report.status === "needs_unit_confirmation" ? <BlockedTable /> : <PendingTable />;
  }
  const unit = unitLabel(pack.currency, pack.unit_scale);
  const items = orderedItems(Object.keys(pack.items));
  const groups = (["income", "balance", "equity", "debt"] as const)
    .map((g) => ({ group: g, items: items.filter((i) => i.group === g) }))
    .filter((g) => g.items.length > 0);

  return (
    <section aria-labelledby="figures-heading">
    <SectionHeading
      id="figures-heading"
      eyebrow="Statements"
      title="Key figures"
      description={
        <>
          As printed in the {pack.basis === "company_only" ? "company" : "consolidated"} statements, in{" "}
          {unit} {pack.currency}. Liabilities are shown as positive amounts; • marks a ratio input.
        </>
      }
      aside={
        <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[0.71875rem] font-medium text-ink-2">
          <span className="num">{unit}</span> {pack.currency}
        </span>
      }
    />
    <Card className="overflow-hidden" data-testid="figures-table">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <caption className="sr-only">Key figures with their source pages and verification state</caption>
          <thead>
            <tr className="border-b border-line bg-surface-sunk/60 text-[0.65625rem] uppercase tracking-[0.08em] text-ink-3">
              <th scope="col" className="px-5 py-2 text-left font-medium">
                Line item
              </th>
              <PeriodHeader period={current} />
              {prior ? <PeriodHeader period={prior} /> : null}
              <th scope="col" className="w-24 px-5 py-2 text-right font-medium">
                Change
              </th>
            </tr>
          </thead>
          {groups.map(({ group, items: rows }) => (
            <tbody key={group} className="[&>tr:last-child]:border-b-0">
              <tr>
                <th
                  colSpan={prior ? 4 : 3}
                  scope="colgroup"
                  className="border-y border-line bg-surface-sunk/70 px-5 pb-1.5 pt-4 text-left text-[0.65625rem] font-semibold uppercase tracking-[0.09em] text-ink-2"
                >
                  {GROUP_TITLES[group]}
                </th>
              </tr>
              {rows.map((item) => (
                <FigureRow key={item.id} item={item} />
              ))}
            </tbody>
          ))}
        </table>
      </div>
    </Card>
    </section>
  );
}

function PeriodHeader({ period }: { period: Period }) {
  return (
    <th scope="col" className="w-32 px-3 py-2 text-right font-medium">
      <Tooltip content={period.end_date ? `Year ended ${period.end_date}` : null}>
        <span tabIndex={0} className="num">
          {period.id}
          {period.is_restated ? <span className="ml-1 normal-case text-amber">restated</span> : null}
        </span>
      </Tooltip>
    </th>
  );
}

function FigureRow({ item }: { item: ItemDef }) {
  const { report, review, current, prior, select, selection } = useReportContext();
  const pack = report.pack!;
  const line = pack.items[item.id];
  const reviewItems = review?.items ?? [];
  const now = cellInfo(report, reviewItems, item.id, current!.id);
  const before = prior ? cellInfo(report, reviewItems, item.id, prior.id) : null;
  const [open, setOpen] = React.useState(false);
  const change = changeFor(report.ratios, item.id, current!.id, prior?.id);
  const selected = selection?.kind === "figure" && selection.item === item.id;
  const derived = now.state === "R3" ? (now.value?.derived_from ?? []) : [];

  return (
    <>
      <tr
        id={`row-${item.id}`}
        data-testid={`figure-row-state-${now.state}`}
        data-item={item.id}
        className={cn(
          "group border-b border-line align-top transition-colors",
          selected ? "bg-accent-soft/50" : "hover:bg-surface-sunk/60",
        )}
      >
        <th scope="row" className="px-5 py-2.5 text-left font-normal">
          <div className="flex items-baseline gap-2">
            <Tooltip content={line?.label_found ? `Printed as “${line.label_found}”` : null}>
              <span
                tabIndex={0}
                data-row-focus
                className={cn("font-medium text-ink", item.ratioInput && "after:ml-1 after:text-ink-3 after:content-['•']")}
              >
                {item.label}
              </span>
            </Tooltip>
          </div>
          <RowDetail
            item={item.id}
            info={now}
            noteRef={line?.note_ref ?? null}
            open={open}
            onToggle={() => setOpen((v) => !v)}
            onOpen={() => select({ kind: "figure", item: item.id, period: current!.id })}
          />
        </th>
        <ValueCell info={now} period={current!.id} item={item.id} />
        {prior && before ? <ValueCell info={before} period={prior.id} item={item.id} secondary /> : null}
        <td className="num px-5 py-2.5 text-right text-[0.8125rem] text-ink-2">
          {change === null ? (
            <span aria-label="not available" className="text-ink-3">—</span>
          ) : (
            <span className="inline-flex items-center justify-end gap-0.5">
              <ChangeArrow text={formatPercentChange(change)} />
              {formatPercentChange(change)}
            </span>
          )}
        </td>
      </tr>
      {open
        ? derived.map((c) => <ComponentRow key={`${c.item}-${c.period_id}`} component={c} colSpan={prior ? 2 : 1} />)
        : null}
    </>
  );
}

/** Direction only, never colour: a rise in a liability is not "good" (UI.md section 10). */
function ChangeArrow({ text }: { text: string }) {
  const d = shownDirection(text);
  const Icon = d > 0 ? ArrowUpRight : d < 0 ? ArrowDownRight : ArrowRight;
  return <Icon aria-hidden className="size-3.5 text-ink-3" />;
}

function changeFor(
  ratios: ReturnType<typeof useReportContext>["report"]["ratios"],
  item: string,
  to: string,
  from: string | undefined,
): number | null {
  if (!ratios || !from) return null;
  const c = ratios.changes.find((x) => x.to_period_id === to && x.from_period_id === from);
  return c?.items[item]?.percent ?? null;
}

function ValueCell({
  info,
  period,
  item,
  secondary = false,
}: {
  info: CellInfo;
  period: string;
  item: string;
  secondary?: boolean;
}) {
  const v = info.value?.value;
  return (
    <td
      className={cn("num px-3 py-2.5 text-right text-[0.875rem]", secondary ? "text-ink-3" : "font-semibold text-ink")}
      data-period={period}
    >
      <div className="flex items-center justify-end gap-1.5">
        {secondary && NOTABLE.includes(info.state) ? (
          <StateBadge
            state={info.state}
            label={info.state === "R3" ? "Derived" : undefined}
            className="px-1.5 text-[0.65625rem]"
          />
        ) : null}
        {v === null || v === undefined ? (
          <span aria-label={`${itemLabel(item)} ${period}: not available`} className="text-ink-3">
            —
          </span>
        ) : (
          <span>{formatFigure(v)}</span>
        )}
      </div>
    </td>
  );
}

function RowDetail({
  item,
  info,
  noteRef,
  open,
  onToggle,
  onOpen,
}: {
  item: string;
  info: CellInfo;
  noteRef: string | null;
  open: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const { report } = useReportContext();
  const v = info.value;
  const chips = (
    <>
      {v?.page ? <PageChip page={v.page} label={v.page_label} onOpen={onOpen} /> : null}
      {noteRef ? <NoteChip note={noteRef} /> : null}
    </>
  );
  const reasons = info.warnings.filter((w) => !["derived_value", "human_override"].includes(w.code));

  switch (info.state) {
    case "R1":
    case "R2":
      return (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {chips}
          <StateBadge
            state={info.state}
            title={info.candidate?.families?.length ? `Engine families: ${info.candidate.families.join(", ")}` : undefined}
          />
        </div>
      );
    case "R3": {
      const n = v?.derived_from?.length ?? 0;
      return (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            data-testid="derived-expander"
            className="inline-flex items-center gap-1 rounded-full text-[0.75rem] text-derived hover:underline"
          >
            <ChevronRight aria-hidden className={cn("size-3.5 transition-transform", open && "rotate-90")} />
            <StateBadge state="R3" label={`Derived: sum of ${n} line${n === 1 ? "" : "s"}`} />
          </button>
        </div>
      );
    }
    case "R4":
      return (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {chips}
          <StateBadge state="R4" title={reasonOf(info.warnings, "human_override")} />
        </div>
      );
    case "R5":
      return (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {chips}
          <StateBadge
            state="R5"
            title={
              <>
                {warningSentence(info.warnings.find((w) => w.code === "human_override_unanchored") ?? fallback(item))}
                <br />
                <CodeHint code="human_override_unanchored" />
              </>
            }
          />
        </div>
      );
    case "R6": {
      const n = info.candidates.length;
      const sentences = reasons.length ? reasons : [];
      const checks = info.candidate?.checks_failed ?? [];
      return (
        <div className="mt-1.5 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <StateBadge
              state="R6"
              label={`Needs review (${n} candidate${n === 1 ? "" : "s"})`}
            />
            {info.candidate?.page ? (
              <PageChip page={info.candidate.page} onOpen={onOpen} />
            ) : null}
            <ReviewButton onOpen={onOpen} />
          </div>
          <WarningList warnings={sentences} fallbackText={checks[0] ? checkSentence(checks[0]) : null} />
        </div>
      );
    }
    case "R7":
      return (
        <div className="mt-1.5 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <StateBadge state="R7" label="Suggested by model: confirm?" />
            <ReviewButton onOpen={onOpen} />
          </div>
          {info.suggestion ? (
            <p className="text-[0.78125rem] leading-relaxed text-ink-2">
              The model points at the row{" "}
              <span className="font-medium text-ink">“{info.suggestion.label}”</span>
              {info.suggestion.page ? ` on p. ${info.suggestion.page}` : ""}. No figure is taken from it
              until a person confirms it.
            </p>
          ) : null}
        </div>
      );
    case "R8":
      return (
        <div className="mt-1.5 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <StateBadge state="R8" />
            {report.status === "ready" || report.status === "needs_document_type" ? <ReviewButton onOpen={onOpen} /> : null}
          </div>
          <WhereWeLooked item={item} />
          <WarningList warnings={reasons.filter((w) => w.code !== "missing_item" || item === "total_debt")} />
        </div>
      );
    case "R9":
      return (
        <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[0.78125rem] text-ink-2">
          <StateBadge state="R9" />
          <span>Not applicable: {info.notApplicable}</span>
        </p>
      );
    default:
      return null;
  }

  function fallback(id: string): PackWarning {
    return { code: "human_override_unanchored", message: "", item: id };
  }
  void report;
}

/** Opens the figure in the evidence panel, where review actions are (UI.md 6.3). */
function ReviewButton({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="open-review"
      className="ml-1 inline-flex h-5 items-center rounded border border-accent/40 px-1.5 text-[0.6875rem] font-medium text-accent hover:bg-accent-soft"
    >
      Review
    </button>
  );
}

function reasonOf(warnings: PackWarning[], code: string): string | undefined {
  const w = warnings.find((x) => x.code === code);
  return w ? warningSentence(w) : undefined;
}

function WarningList({ warnings, fallbackText = null }: { warnings: PackWarning[]; fallbackText?: string | null }) {
  const seen = new Set<string>();
  const lines = warnings
    .map((w) => ({ text: warningSentence(w), code: w.code }))
    .filter((l) => (seen.has(l.text) ? false : (seen.add(l.text), true)));
  if (!lines.length && !fallbackText) return null;
  return (
    <ul className="space-y-0.5 text-[0.78125rem] leading-relaxed text-ink-2">
      {lines.map((l) => (
        <li key={l.text}>
          <Tooltip content={<CodeHint code={l.code} />}>
            <span tabIndex={0} data-testid="warning-sentence">
              {l.text}
            </span>
          </Tooltip>
        </li>
      ))}
      {!lines.length && fallbackText ? <li>{fallbackText}</li> : null}
    </ul>
  );
}

/** R8: "Searched the consolidated income statement (pp. 142–143) for: revenue, turnover…" */
function WhereWeLooked({ item }: { item: string }) {
  const { report, current } = useReportContext();
  const where = report.extraction?.searched_for?.[item];
  const decision = report.extraction?.candidates?.[`${item}:${current?.id}`]?.decision;
  if (!where) return null;
  const statement = STATEMENT_NAMES[where.statement] ?? where.statement.replace(/_/g, " ");
  const pages = where.pages.length ? ` (${pageRange(where.pages)})` : "";
  const extra = decision && DECISION_SENTENCES[decision] && item !== "total_debt" ? ` ${DECISION_SENTENCES[decision]}` : "";
  if (where.components.length) {
    return (
      <p data-testid="where-we-looked" className="text-[0.78125rem] leading-relaxed text-ink-2">
        Searched the {statement}
        {pages} for its components:{" "}
        <Tooltip content={where.labels.length ? `Labels tried: ${where.labels.join(", ")}` : null}>
          <span tabIndex={0} className="underline decoration-dotted underline-offset-2">
            borrowings and lease liabilities, current and non-current
          </span>
        </Tooltip>
        .{extra}
      </p>
    );
  }
  const labels = where.labels.length ? ` for ${where.labels.join(", ")}` : "";
  return (
    <p data-testid="where-we-looked" className="text-[0.78125rem] leading-relaxed text-ink-2">
      Searched the {statement}
      {pages}
      {labels}.{extra}
    </p>
  );
}

function ComponentRow({ component, colSpan }: { component: DerivedComponent; colSpan: number }) {
  const { report, select } = useReportContext();
  const v = report.pack?.items[component.item]?.values.find((x) => x.period_id === component.period_id);
  return (
    <tr data-testid="derived-component" className="border-b border-line bg-derived-soft/30 text-[0.8125rem]">
      <th scope="row" className="py-2 pl-11 pr-5 text-left font-normal text-ink-2">
        <span>{itemLabel(component.item)}</span>
        <span className="ml-2 inline-flex items-center gap-1.5 align-middle">
          {component.assumed_zero ? (
            <span className="text-[0.75rem] text-ink-3">Not presented (section fully checked)</span>
          ) : v?.page ? (
            <PageChip
              page={v.page}
              label={v.page_label}
              onOpen={() => select({ kind: "figure", item: component.item, period: component.period_id })}
            />
          ) : null}
        </span>
      </th>
      <td className="num px-3 py-2 text-right text-ink-2">
        {component.assumed_zero ? "0" : v?.value != null ? formatFigure(v.value) : "—"}
      </td>
      {colSpan > 1 ? <td /> : null}
      <td />
    </tr>
  );
}

/** Before extraction has finished: nothing to show yet, and nothing guessed. */
function PendingTable() {
  const { report } = useReportContext();
  return (
    <Card className="px-5 py-4" data-testid="figures-pending">
      <h2 className="text-[0.9375rem] font-semibold tracking-[-0.01em]">Key figures</h2>
      <p className="mt-1 text-[0.8125rem] text-ink-2">
        {report.status === "failed"
          ? "No figures: extraction did not finish."
          : "Figures appear here as soon as the statements have been read and checked."}
      </p>
    </Card>
  );
}

/** R10: the unit is not confirmed, so no figure is shown at all (UI.md section 4). */
function BlockedTable() {
  const rows = ITEMS.filter((i) => i.ratioInput);
  return (
    <Card className="relative overflow-hidden" data-testid="figures-table">
      <div className="border-b border-line px-5 py-3.5">
        <h2 className="text-[0.9375rem] font-semibold tracking-[-0.01em]">Key figures</h2>
      </div>
      <div aria-hidden className="pointer-events-none select-none opacity-40 grayscale">
        <table className="w-full text-sm">
          <tbody>
            {rows.map((i) => (
              <tr key={i.id} data-testid="figure-row-state-R10" className="border-b border-line last:border-b-0">
                <th scope="row" className="px-5 py-3 text-left font-medium text-ink-2">
                  {i.label}
                </th>
                <td className="px-3 py-3 text-right">
                  <span className="inline-block h-3 w-16 rounded bg-surface-sunk" />
                </td>
                <td className="px-5 py-3 text-right">
                  <span className="inline-block h-3 w-14 rounded bg-surface-sunk" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="absolute inset-0 top-12 flex items-center justify-center">
        <div className="flex max-w-sm flex-col items-center gap-2 rounded-xl border border-line bg-surface/95 px-6 py-5 text-center shadow-[var(--shadow-pop)] backdrop-blur">
          <Lock aria-hidden className="size-5 text-ink-3" />
          <p className="text-sm font-semibold text-ink">Confirm the unit to see figures</p>
          <p className="text-[0.78125rem] leading-relaxed text-ink-2">
            The statement headers don’t say whether figures are in units, thousands or millions, so
            none are shown until a person confirms it.
          </p>
          <a href="#banner-unit" className="text-[0.78125rem] font-medium text-accent hover:underline">
            Why is this blocked?
          </a>
        </div>
      </div>
    </Card>
  );
}

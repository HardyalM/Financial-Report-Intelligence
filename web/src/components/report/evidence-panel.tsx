"use client";

import { Check, MousePointerClick, Quote, X } from "lucide-react";
import * as React from "react";
import { CodeHint, StateBadge } from "@/components/report/chips";
import { useReportContext, type Selection } from "@/components/report/context";
import { type Highlight, PdfViewer } from "@/components/report/pdf-viewer";
import { ReviewPanel } from "@/components/report/review-panel";
import { Badge } from "@/components/ui/badge";
import { warningSentence } from "@/lib/copy";
import { pageRange, unitLabel } from "@/lib/format";
import { FAMILY_NAMES, itemLabel } from "@/lib/items";
import { cellInfo } from "@/lib/states";
import type { ArithmeticCheck, Candidate, Citation, Report, ReportedMetric } from "@/lib/types";

/** True from 1280 px: the panel sits beside the report; below that it is a bottom sheet. */
function useWide(): boolean {
  const query = "(min-width: 1280px)";
  return React.useSyncExternalStore(
    (notify) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", notify);
      return () => m.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => true,
  );
}

/**
 * The evidence panel (UI.md section 6): the PDF page with the source highlighted (D1) and its
 * provenance (D2). Sticky beside the report from 1280 px; a bottom sheet below that (Esc closes).
 */
export function EvidencePanel() {
  const { selection, select } = useReportContext();
  const wide = useWide();
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && select(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [select]);

  if (wide) {
    return (
      <aside
        aria-label="Evidence"
        data-testid="evidence-panel"
        className="sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto rounded-xl border border-line bg-surface shadow-[var(--shadow-card)]"
      >
        <PanelBody />
      </aside>
    );
  }
  if (!selection) return null;
  return (
    <div
      role="dialog"
      aria-label="Evidence"
      data-testid="evidence-panel"
      className="fixed inset-x-0 bottom-0 z-40 max-h-[75vh] overflow-y-auto rounded-t-2xl border-t border-line bg-surface shadow-[var(--shadow-pop)]"
    >
      <div className="flex justify-end px-3 pt-2">
        <button
          type="button"
          onClick={() => select(null)}
          aria-label="Close evidence"
          className="rounded p-1.5 text-ink-3 hover:bg-surface-sunk hover:text-ink"
        >
          <X aria-hidden className="size-4" />
        </button>
      </div>
      <PanelBody />
    </div>
  );
}

interface Target {
  page: number | null;
  highlights: Highlight[];
}

function targetOf(report: Report, selection: Selection): Target {
  if (!selection) return { page: null, highlights: [] };
  if (selection.kind === "citation") {
    const c = selection.citation;
    return {
      page: c.page,
      highlights: c.bbox
        .filter((b) => b.length === 5)
        .map(([page, x0, y0, x1, y1]) => ({ page: page!, x0: x0!, y0: y0!, x1: x1!, y1: y1!, space: "display" as const })),
    };
  }
  if (selection.kind === "pages") return { page: selection.pages[0] ?? null, highlights: [] };
  if (selection.kind === "reported") return { page: selection.metric.page, highlights: [] };
  const v = report.pack?.items[selection.item]?.values.find((x) => x.period_id === selection.period);
  const candidate = report.extraction?.candidates?.[`${selection.item}:${selection.period}`];
  const page = v?.page ?? candidate?.page ?? null;
  const box = v?.bbox;
  return {
    page,
    highlights:
      page && box ? [{ page, x0: box[0], y0: box[1], x1: box[2], y1: box[3], space: "unrotated" }] : [],
  };
}

function PanelBody() {
  const { selection, report } = useReportContext();
  const target = React.useMemo(() => targetOf(report, selection), [report, selection]);
  const offset = report.extraction?.folio_offset;
  const folio = React.useCallback(
    (page: number) => {
      if (selection?.kind === "citation" && selection.citation.page === page && selection.citation.page_label) {
        return selection.citation.page_label;
      }
      return typeof offset === "number" && page - offset > 0 ? String(page - offset) : null;
    },
    [offset, selection],
  );
  if (!selection) {
    return (
      <div className="flex min-h-64 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
        <MousePointerClick aria-hidden className="size-5 text-ink-3" />
        <p className="max-w-[16rem] text-[13px] leading-relaxed text-ink-3" data-testid="evidence-empty">
          Select a figure, ratio input or citation to see its source.
        </p>
      </div>
    );
  }
  return (
    <div>
      {target.page ? (
        <PdfViewer
          url={`/api/reports/${report.id}/original`}
          page={target.page}
          highlights={target.highlights}
          folio={folio}
        />
      ) : null}
      {selection.kind === "citation" ? (
        <CitationProvenance citation={selection.citation} n={selection.n} />
      ) : selection.kind === "reported" ? (
        <ReportedProvenance metric={selection.metric} />
      ) : selection.kind === "pages" ? (
        <div className="space-y-2 px-5 py-4" data-testid="provenance-card">
          <h3 className="text-[15px] font-semibold text-ink">{selection.label}</h3>
          <p className="text-[12.5px] leading-relaxed text-ink-2">{selection.note}</p>
          <p className="num text-[12.5px] text-ink-3">Printed on {pageRange(selection.pages)}</p>
        </div>
      ) : (
        <>
          <FigureProvenance item={selection.item} period={selection.period} input={selection.kind === "input"} />
          <ReviewPanel item={selection.item} period={selection.period} />
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------------- figures

/** Which items each arithmetic check speaks for (EXTRACTION section 5.2). */
function checkCovers(name: string, item: string): boolean {
  if (name === "profit_before_tax_chain") return item === "profit_before_tax" || item === "operating_profit";
  if (name === "net_income_chain") return item === "net_income" || item === "profit_before_tax";
  return name.startsWith(`${item}_`);
}

function checkText(check: Pick<ArithmeticCheck, "name" | "detail">): string {
  const name = check.name.replace(/_(chain|section_sum|components)$/, "");
  const words = check.detail.replace(/[a-z]+(?:_[a-z]+)+/g, (id) => itemLabel(id).toLowerCase());
  return `${itemLabel(name)} = ${/^\d/.test(words) ? `sum of ${words}` : words}`;
}

function FigureProvenance({ item, period, input }: { item: string; period: string; input: boolean }) {
  const { report, review } = useReportContext();
  const pack = report.pack;
  const line = pack?.items[item];
  const info = cellInfo(report, review?.items ?? [], item, period);
  const v = info.value;
  const c: Candidate | null = info.candidate;
  const checks = (report.extraction?.checks ?? []).filter((k) => k.period === period && checkCovers(k.name, item));
  const families = c?.families ?? [];
  const engines = c?.engines ?? [];
  return (
    <div className="space-y-4 px-5 py-4" data-testid="provenance-card">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">
          {input ? "Ratio input" : "Figure"} · {period}
        </p>
        <h3 className="mt-0.5 text-[15px] font-semibold text-ink">{itemLabel(item)}</h3>
        {line?.label_found ? <p className="text-[12.5px] text-ink-3">Printed as “{line.label_found}”</p> : null}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[12.5px]">
        <Row term="As printed">
          {v?.raw_text ?? c?.raw_text ? (
            <span className="font-mono text-ink">{v?.raw_text ?? c?.raw_text}</span>
          ) : (
            <span className="text-ink-3">—</span>
          )}
        </Row>
        <Row term="Page">
          {v?.page ?? c?.page ? (
            <span className="num">
              PDF p.&nbsp;{v?.page ?? c?.page}
              {v?.page_label ? ` · printed p. ${v.page_label}` : ""}
            </span>
          ) : (
            <span className="text-ink-3">—</span>
          )}
        </Row>
        {line?.note_ref ? <Row term="Note">{line.note_ref}</Row> : null}
        {v?.page && !v.bbox ? (
          <Row term="Position">
            <span data-testid="no-position">
              Not recorded{v.engine?.startsWith("human_override") ? " (set by a person)" : ""}, so nothing is
              highlighted on the page.
            </span>
          </Row>
        ) : null}
        <Row term="Unit">
          {unitLabel(pack?.currency, pack?.unit_scale)} {pack?.currency}
        </Row>
      </dl>

      <section data-testid="provenance-families">
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">Engine families</h4>
        <p className="mt-1 text-[12.5px] text-ink-2">
          {families.length
            ? `${families.map((f) => FAMILY_NAMES[f] ?? f).join(" and ")} ${families.length > 1 ? "agree" : "only"}`
            : v?.engine === "derived"
              ? "Derived in code from printed lines"
              : v?.engine?.startsWith("human_override")
                ? "Entered by a person"
                : "No engine read a value"}
          {engines.length ? <span className="text-ink-3"> · engines: {engines.join(", ")}</span> : null}
        </p>
        <div className="mt-1.5">
          <StateBadge state={info.state} />
        </div>
      </section>

      <section data-testid="provenance-checks">
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">Checks</h4>
        {checks.length ? (
          <ul className="mt-1 space-y-1 text-[12.5px]">
            {dedupe(checks).map((k) => (
              <li key={`${k.name}-${k.engine}`} className="flex items-start gap-1.5">
                <span aria-hidden className={k.passed ? "text-ok" : "text-missing"}>
                  {k.passed ? "✓" : "✗"}
                </span>
                <span className="text-ink-2">
                  {checkText(k)}
                  <span className="sr-only">{k.passed ? " passed" : " failed"}</span>
                  {!k.passed ? <span className="num text-ink-3"> (off by {k.difference.replace(/^-/, "")})</span> : null}
                  <span className="text-ink-3"> · {k.engine}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[12.5px] text-ink-3">No arithmetic check covers this line.</p>
        )}
      </section>

      {info.warnings.length ? (
        <ul className="space-y-1 text-[12.5px] leading-relaxed text-ink-2">
          {info.warnings.map((w, i) => (
            <li key={i}>
              {warningSentence(w)} <CodeHint code={w.code} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function dedupe(checks: ArithmeticCheck[]): ArithmeticCheck[] {
  const seen = new Set<string>();
  return checks.filter((k) => {
    const key = `${k.name}|${k.engine}|${k.passed}`;
    return seen.has(key) ? false : (seen.add(key), true);
  });
}

// --------------------------------------------------------------------------------- citations

function CitationProvenance({ citation, n }: { citation: Citation; n: number }) {
  const path = citation.heading_path.slice(1);
  return (
    <div className="space-y-4 px-5 py-4" data-testid="provenance-card">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">Citation {n}</p>
        <h3 className="mt-0.5 text-[14px] font-semibold leading-snug text-ink" data-testid="citation-section">
          {path.length ? path.join(" › ") : citation.section.replace(/_/g, " ")}
        </h3>
      </div>
      <blockquote className="relative rounded-lg border border-line bg-surface-sunk/60 py-2.5 pl-8 pr-3 text-[13px] leading-relaxed text-ink">
        <Quote aria-hidden className="absolute left-2.5 top-3 size-3.5 text-ink-3" />
        <span data-testid="citation-quote">{citation.quote}</span>
      </blockquote>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[12.5px]">
        <Row term="Page">
          <span className="num">
            PDF {citation.page_end > citation.page ? `pp. ${citation.page}–${citation.page_end}` : `p. ${citation.page}`}
            {citation.page_label ? ` · printed p. ${citation.page_label}` : ""}
          </span>
        </Row>
        {citation.note_number ? <Row term="Note">{citation.note_number}</Row> : null}
        <Row term="Match">
          <Badge tone={citation.match === "exact" ? "ok" : "single"} data-testid="citation-match">
            <Check aria-hidden />
            {citation.match === "exact" ? "Exact quote" : "Matched after normalising spacing and punctuation"}
          </Badge>
        </Row>
        {citation.is_footnote ? <Row term="Source">A footnote</Row> : null}
      </dl>
    </div>
  );
}

// --------------------------------------------------------------------------------- reported

function ReportedProvenance({ metric }: { metric: ReportedMetric }) {
  return (
    <div className="space-y-4 px-5 py-4" data-testid="provenance-card">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">
          Reported by the company · {metric.period_id ?? "period not stated"}
        </p>
        <h3 className="mt-0.5 text-[15px] font-semibold text-ink">{metric.label}</h3>
        <p className="text-[12.5px] text-ink-3">Printed as “{metric.label_found}”</p>
      </div>
      <blockquote className="relative rounded-lg border border-line bg-surface-sunk/60 py-2.5 pl-8 pr-3 text-[13px] leading-relaxed text-ink">
        <Quote aria-hidden className="absolute left-2.5 top-3 size-3.5 text-ink-3" />
        <span data-testid="reported-quote">{metric.quote}</span>
      </blockquote>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[12.5px]">
        <Row term="As printed">
          <span className="font-mono text-ink">{metric.value_text}</span>
        </Row>
        <Row term="Page">
          <span className="num">
            PDF p.&nbsp;{metric.page}
            {metric.page_label ? ` · printed p. ${metric.page_label}` : ""}
          </span>
        </Row>
        {metric.basis ? <Row term="Basis">{metric.basis}</Row> : null}
      </dl>
      <p className="text-[12px] leading-relaxed text-ink-3" data-testid="reported-note">
        The company’s own figure, quoted. It is not computed here and never feeds a ratio.
      </p>
    </div>
  );
}

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-ink-3">{term}</dt>
      <dd className="text-ink-2">{children}</dd>
    </>
  );
}

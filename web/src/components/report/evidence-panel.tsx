"use client";

import { Check, MousePointerClick, Quote, X } from "lucide-react";
import { AnimatePresence, motion, useDragControls } from "motion/react";
import * as React from "react";
import { CodeHint, StateBadge } from "@/components/report/chips";
import { useReportContext, type Selection } from "@/components/report/context";
import { type Highlight, PdfViewer } from "@/components/report/pdf-viewer";
import { ReviewPanel } from "@/components/report/review-panel";
import { Badge } from "@/components/ui/badge";
import { warningSentence } from "@/lib/copy";
import { pageRange, unitLabel } from "@/lib/format";
import { CloseButton } from "@/components/ui/close-button";
import { project, spring, useSafeMotion } from "@/lib/motion";
import { warmRenderer } from "@/lib/pdf-renderer";
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
  const { selection, select, report } = useReportContext();
  const wide = useWide();
  // The original is opened in the render worker while the reader looks at the figures.
  React.useEffect(() => (report.page_count ? warmRenderer(`/api/reports/${report.id}/original`) : undefined), [report.id, report.page_count]);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && select(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [select]);

  // Click off the source: a plain click on empty space in the report (not on a control, a chip,
  // a figure or citation, not a drag or a text selection) puts the PDF away, like clicking off a
  // selected item on a desktop.
  React.useEffect(() => {
    if (!selection) return;
    let press: { x: number; y: number } | null = null;
    const ignore = (t: Element | null) =>
      !t ||
      !!t.closest(
        "[data-testid=evidence-panel], [data-testid=pdf-reader], [role=dialog], [role=menu], header, nav, aside, " +
          "a, button, input, textarea, select, label, summary, [role=button], [role=tab], [role=option], [tabindex], [data-placeholder]",
      );
    const down = (e: PointerEvent) => {
      press = e.button === 0 && !ignore(e.target as Element) ? { x: e.clientX, y: e.clientY } : null;
    };
    const up = (e: PointerEvent) => {
      const p = press;
      press = null;
      if (!p || ignore(e.target as Element) || Math.hypot(e.clientX - p.x, e.clientY - p.y) > 5) return;
      if (window.getSelection()?.toString()) return;
      select(null);
    };
    document.addEventListener("pointerdown", down, true);
    document.addEventListener("pointerup", up, true);
    return () => {
      document.removeEventListener("pointerdown", down, true);
      document.removeEventListener("pointerup", up, true);
    };
  }, [selection, select]);

  if (wide) {
    return (
      <aside
        aria-label="Evidence"
        data-testid="evidence-panel"
        className="sticky top-[7.5rem] max-h-[calc(100vh-9rem)] overflow-y-auto rounded-2xl border border-line bg-surface shadow-[var(--shadow-raised)]"
      >
        <PanelBody onClose={selection ? () => select(null) : undefined} />
      </aside>
    );
  }
  return (
    <AnimatePresence>
      {selection ? <EvidenceSheet key="sheet" onClose={() => select(null)} /> : null}
    </AnimatePresence>
  );
}

/**
 * Below 1280 px the evidence is a bottom sheet. It rises from the bottom and leaves the same way;
 * tap the dimmed page behind it to close it, or drag its handle: the sheet follows the finger
 * 1:1 from where it was grabbed, resists being pulled up, and on release goes where the flick
 * would carry it (closed if it would land past a third of its height, back otherwise).
 */
function EvidenceSheet({ onClose }: { onClose: () => void }) {
  const drag = useDragControls();
  const sheet = React.useRef<HTMLDivElement>(null);
  const safe = useSafeMotion(); // reduced motion: these fade instead of moving
  return (
    <>
      <motion.div
        key="scrim"
        aria-hidden
        data-testid="evidence-scrim"
        className="fixed inset-0 z-[55] bg-[oklch(0.15_0.02_262/0.28)]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={spring.modal}
        onClick={onClose}
      />
      <motion.div
        ref={sheet}
        role="dialog"
        aria-label="Evidence"
        data-testid="evidence-panel"
        className="fixed inset-x-0 bottom-0 z-[55] flex max-h-[75vh] flex-col rounded-t-2xl border-t border-line bg-surface shadow-[var(--shadow-pop)]"
        initial={safe({ y: "100%", opacity: 0 })}
        animate={safe({ y: 0, opacity: 1 })}
        exit={safe({ y: "100%", opacity: 0 })}
        transition={spring.modal}
        drag="y"
        dragListener={false}
        dragControls={drag}
        dragConstraints={{ top: 0, bottom: 0 }}
        dragElastic={{ top: 0.08, bottom: 1 }}
        dragSnapToOrigin
        dragTransition={{ bounceStiffness: 420, bounceDamping: 32 }}
        onDragEnd={(_, info) => {
          const height = sheet.current?.offsetHeight ?? 400;
          if (info.offset.y + project(info.velocity.y) > height / 3) onClose();
        }}
      >
        <div
          className="flex shrink-0 cursor-grab touch-none items-center justify-between px-3 pb-1 pt-2 active:cursor-grabbing"
          onPointerDown={(e) => drag.start(e)}
          data-testid="evidence-handle"
        >
          <span className="w-8" />
          <span aria-hidden className="h-1.5 w-10 rounded-full bg-ink/15" />
          <button
            type="button"
            onClick={onClose}
            onPointerDown={(e) => e.stopPropagation()}
            aria-label="Close evidence"
            className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-sunk hover:text-ink"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <PanelBody />
        </div>
      </motion.div>
    </>
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

function PanelBody({ onClose }: { onClose?: () => void }) {
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
      <div>
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <span className="eyebrow">Evidence</span>
          <span className="text-[0.71875rem] text-ink-3">Source page · provenance</span>
        </div>
        <div className="flex min-h-72 flex-col items-center justify-center gap-4 px-8 py-12 text-center">
          <span className="relative flex size-12 items-center justify-center rounded-2xl border border-line bg-surface-sunk">
            <MousePointerClick aria-hidden className="size-5 text-ink-2" />
          </span>
          <p className="max-w-[17rem] text-[0.8125rem] leading-relaxed text-ink-2" data-testid="evidence-empty">
            Select a figure, ratio input or citation to see its source.
          </p>
          <ul className="w-full max-w-[17rem] space-y-1.5 text-left text-[0.75rem] text-ink-3">
            <li className="flex gap-2"><span className="num text-ink-2">1</span>The PDF page, with the cell or quote highlighted</li>
            <li className="flex gap-2"><span className="num text-ink-2">2</span>The text as printed and the arithmetic checks</li>
            <li className="flex gap-2"><span className="num text-ink-2">3</span>Review actions when a figure needs a decision</li>
          </ul>
        </div>
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
          onClose={onClose}
        />
      ) : onClose ? (
        <div className="flex items-center justify-between border-b border-line px-4 py-2">
          <span className="eyebrow">Evidence</span>
          <CloseButton onClose={onClose} />
        </div>
      ) : null}
      {selection.kind === "citation" ? (
        <CitationProvenance citation={selection.citation} n={selection.n} />
      ) : selection.kind === "reported" ? (
        <ReportedProvenance metric={selection.metric} />
      ) : selection.kind === "pages" ? (
        <div className="space-y-2 px-5 py-4" data-testid="provenance-card">
          <h3 className="text-[0.9375rem] font-semibold text-ink">{selection.label}</h3>
          <p className="text-[0.78125rem] leading-relaxed text-ink-2">{selection.note}</p>
          <p className="num text-[0.78125rem] text-ink-3">Printed on {pageRange(selection.pages)}</p>
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
        <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.07em] text-ink-3">
          {input ? "Ratio input" : "Figure"} · {period}
        </p>
        <h3 className="mt-0.5 text-[0.9375rem] font-semibold text-ink">{itemLabel(item)}</h3>
        {line?.label_found ? <p className="text-[0.78125rem] text-ink-3">Printed as “{line.label_found}”</p> : null}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[0.78125rem]">
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
        <h4 className="text-[0.6875rem] font-semibold uppercase tracking-[0.07em] text-ink-3">Engine families</h4>
        <p className="mt-1 text-[0.78125rem] text-ink-2">
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
        <h4 className="text-[0.6875rem] font-semibold uppercase tracking-[0.07em] text-ink-3">Checks</h4>
        {checks.length ? (
          <ul className="mt-1 space-y-1 text-[0.78125rem]">
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
          <p className="mt-1 text-[0.78125rem] text-ink-3">No arithmetic check covers this line.</p>
        )}
      </section>

      {info.warnings.length ? (
        <ul className="space-y-1 text-[0.78125rem] leading-relaxed text-ink-2">
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
        <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.07em] text-ink-3">Citation {n}</p>
        <h3 className="mt-0.5 text-[0.875rem] font-semibold leading-snug text-ink" data-testid="citation-section">
          {path.length ? path.join(" › ") : citation.section.replace(/_/g, " ")}
        </h3>
      </div>
      <blockquote className="relative rounded-lg border border-line bg-surface-sunk/60 py-2.5 pl-8 pr-3 text-[0.8125rem] leading-relaxed text-ink">
        <Quote aria-hidden className="absolute left-2.5 top-3 size-3.5 text-ink-3" />
        <span data-testid="citation-quote">{citation.quote}</span>
      </blockquote>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[0.78125rem]">
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
        <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.07em] text-ink-3">
          Reported by the company · {metric.period_id ?? "period not stated"}
        </p>
        <h3 className="mt-0.5 text-[0.9375rem] font-semibold text-ink">{metric.label}</h3>
        <p className="text-[0.78125rem] text-ink-3">Printed as “{metric.label_found}”</p>
      </div>
      <blockquote className="relative rounded-lg border border-line bg-surface-sunk/60 py-2.5 pl-8 pr-3 text-[0.8125rem] leading-relaxed text-ink">
        <Quote aria-hidden className="absolute left-2.5 top-3 size-3.5 text-ink-3" />
        <span data-testid="reported-quote">{metric.quote}</span>
      </blockquote>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[0.78125rem]">
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
      <p className="text-[0.75rem] leading-relaxed text-ink-3" data-testid="reported-note">
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

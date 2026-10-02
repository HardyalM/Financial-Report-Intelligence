"use client";

import { MousePointerClick, X } from "lucide-react";
import * as React from "react";
import { CodeHint, StateBadge } from "@/components/report/chips";
import { useReportContext } from "@/components/report/context";
import { cn } from "@/lib/cn";
import { warningSentence } from "@/lib/copy";
import { unitLabel } from "@/lib/format";
import { FAMILY_NAMES, itemLabel } from "@/lib/items";
import { cellInfo } from "@/lib/states";

/**
 * The evidence panel (UI.md section 6): sticky beside the report from 1280 px, a bottom sheet
 * below that. M7.1 shows the provenance of a figure; the PDF viewer and citations arrive in M7.2.
 */
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
  return (
    <>
      {selection ? (
        <div
          role="dialog"
          aria-label="Evidence"
          data-testid="evidence-sheet"
          className="fixed inset-x-0 bottom-0 z-40 max-h-[60vh] overflow-y-auto rounded-t-2xl border-t border-line bg-surface shadow-[var(--shadow-pop)]"
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
      ) : null}
    </>
  );
}

function PanelBody() {
  const { selection, report, review } = useReportContext();
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
  const pack = report.pack;
  const line = pack?.items[selection.item];
  const info = cellInfo(report, review?.items ?? [], selection.item, selection.period);
  const v = info.value;
  const c = info.candidate;
  const families = c?.families ?? [];
  return (
    <div className="space-y-4 px-5 py-4" data-testid="provenance-card">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">
          {selection.kind === "input" ? "Ratio input" : "Figure"} · {selection.period}
        </p>
        <h3 className="mt-0.5 text-[15px] font-semibold text-ink">{itemLabel(selection.item)}</h3>
        {line?.label_found ? <p className="text-[12.5px] text-ink-3">Printed as “{line.label_found}”</p> : null}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[12.5px]">
        <Row term="As printed">
          {v?.raw_text ? <span className="font-mono text-ink">{v.raw_text}</span> : <span className="text-ink-3">—</span>}
        </Row>
        <Row term="Page">
          {v?.page ? (
            <span className="num">
              PDF p.&nbsp;{v.page}
              {v.page_label ? ` · printed p. ${v.page_label}` : ""}
            </span>
          ) : (
            <span className="text-ink-3">—</span>
          )}
        </Row>
        {line?.note_ref ? <Row term="Note">{line.note_ref}</Row> : null}
        <Row term="Unit">
          {unitLabel(pack?.currency, pack?.unit_scale)} {pack?.currency}
        </Row>
        <Row term="Engines">
          {families.length ? families.map((f) => FAMILY_NAMES[f] ?? f).join(" + ") : v?.engine ?? "—"}
        </Row>
      </dl>
      <div>
        <StateBadge state={info.state} />
      </div>
      {c?.checks_passed?.length || c?.checks_failed?.length ? (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">Checks</p>
          <ul className="mt-1 space-y-0.5 text-[12.5px]" data-testid="provenance-checks">
            {[...new Set(c.checks_passed ?? [])].map((n) => (
              <li key={`p-${n}`} className="text-ok">✓ {n.replace(/_/g, " ")}</li>
            ))}
            {[...new Set(c.checks_failed ?? [])].map((n) => (
              <li key={`f-${n}`} className="text-missing">✗ {n.split(":")[0]!.replace(/_/g, " ")}</li>
            ))}
          </ul>
        </div>
      ) : null}
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

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <>
      <dt className={cn("text-ink-3")}>{term}</dt>
      <dd className="text-ink-2">{children}</dd>
    </>
  );
}

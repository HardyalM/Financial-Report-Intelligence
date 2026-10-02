"use client";

import { CircleDashed, FileWarning, Lock, RefreshCw, ScanText, ShieldHalf, X } from "lucide-react";
import * as React from "react";
import { useReportContext } from "@/components/report/context";
import { cn } from "@/lib/cn";
import { warningSentence } from "@/lib/copy";
import { STATEMENT_NAMES } from "@/lib/items";

interface BannerDef {
  id: string;
  tone: "block" | "warn" | "info";
  Icon: typeof Lock;
  title: string;
  body: React.ReactNode;
  dismissible: boolean;
}

/** Banners, highest priority first (UI.md section 8). Each explains; dismissal lasts the session. */
export function BannerStack() {
  const { report, commentary } = useReportContext();
  const [dismissed, setDismissed] = React.useState<Set<string>>(() => new Set());
  React.useEffect(() => {
    try {
      const raw = sessionStorage.getItem(`banners:${report.id}`);
      if (raw) setDismissed(new Set(JSON.parse(raw) as string[]));
    } catch {
      /* storage unavailable: banners simply show */
    }
  }, [report.id]);
  const dismiss = (id: string) => {
    const next = new Set(dismissed).add(id);
    setDismissed(next);
    try {
      sessionStorage.setItem(`banners:${report.id}`, JSON.stringify([...next]));
    } catch {
      /* ignore */
    }
  };

  const pack = report.pack;
  const warnings = pack?.warnings ?? [];
  const banners: BannerDef[] = [];
  if (report.status === "needs_unit_confirmation") {
    banners.push({
      id: "unit", tone: "block", Icon: Lock, dismissible: false,
      title: "The unit or currency needs confirming",
      body: "No unit was printed in the statement headers, so it isn’t clear whether figures are in units, thousands or millions. Nothing is shown until a person confirms it from the page; the pipeline never guesses.",
    });
  }
  const docType = warnings.find((w) => w.code === "document_type_ambiguous");
  if (report.status === "needs_document_type" || docType) {
    const signals = docType ? /\(([^)]*)\)/.exec(docType.message)?.[1] : null;
    banners.push({
      id: "document-type", tone: "block", Icon: CircleDashed, dismissible: false,
      title: "Document type unclear: ratios are withheld",
      body: (
        <>
          Corporate, bank, NHS trust and other reports use different ratios, and the signals in this report
          don’t settle which it is.{signals ? <> Signals found: <span className="text-ink">{signals}</span>.</> : null}
        </>
      ),
    });
  }
  for (const key of ["income_statement", "balance_sheet"]) {
    const s = report.extraction?.statements?.[key];
    if (s && s.status !== "found") {
      banners.push({
        id: `statement-${key}`, tone: "warn", Icon: FileWarning, dismissible: true,
        title: `The ${STATEMENT_NAMES[key]} was not found`,
        body: "Its figures are empty rather than taken from another statement.",
      });
    }
  }
  if (report.reduced_verification) {
    const w = warnings.find((x) => x.code === "reduced_verification");
    banners.push({
      id: "reduced", tone: "info", Icon: ShieldHalf, dismissible: true,
      title: "Reduced verification",
      body: w ? warningSentence(w) : "Only one engine family read the statements.",
    });
  }
  const born = warnings.find((w) => w.code === "not_digitally_born");
  if (born) {
    banners.push({
      id: "born", tone: "warn", Icon: ScanText, dismissible: true,
      title: "Not digitally born", body: warningSentence(born),
    });
  }
  if (report.stale || commentary?.stale) {
    banners.push({
      id: "stale", tone: "warn", Icon: RefreshCw, dismissible: true,
      title: "Figures changed since this commentary was written",
      body: "The commentary below describes an earlier version of the figures.",
    });
  }

  const shown = banners.filter((b) => !(b.dismissible && dismissed.has(b.id)));
  if (!shown.length) return null;
  return (
    <div className="space-y-2" data-testid="banner-stack">
      {shown.map((b) => (
        <div
          key={b.id}
          id={`banner-${b.id}`}
          role={b.tone === "block" ? "alert" : "status"}
          data-testid={`banner-${b.id}`}
          className={cn(
            "flex scroll-mt-6 items-start gap-3 rounded-xl border px-4 py-3",
            b.tone === "block" && "border-review-line bg-review-soft",
            b.tone === "warn" && "border-amber-line bg-amber-soft",
            b.tone === "info" && "border-line bg-surface",
          )}
        >
          <b.Icon
            aria-hidden
            className={cn(
              "mt-0.5 size-4 shrink-0",
              b.tone === "block" ? "text-review" : b.tone === "warn" ? "text-amber" : "text-ink-3",
            )}
          />
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-semibold text-ink">{b.title}</p>
            <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-2">{b.body}</p>
          </div>
          {b.dismissible ? (
            <button
              type="button"
              onClick={() => dismiss(b.id)}
              className="rounded p-1 text-ink-3 hover:bg-surface-sunk hover:text-ink"
              aria-label={`Dismiss: ${b.title}`}
            >
              <X aria-hidden className="size-3.5" />
            </button>
          ) : null}
        </div>
      ))}
    </div>
  );
}


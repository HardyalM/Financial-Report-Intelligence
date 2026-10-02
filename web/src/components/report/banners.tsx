"use client";

import { CircleDashed, FileWarning, Lock, RefreshCw, ScanText, ShieldHalf, X } from "lucide-react";
import * as React from "react";
import { useReportContext } from "@/components/report/context";
import { PointToPage } from "@/components/report/review-panel";
import { Button } from "@/components/ui/button";
import { ApiError, decisions } from "@/lib/api";
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
  /** The one action that resolves the banner (UI.md section 8). */
  action?: React.ReactNode;
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
      action: <DocumentTypeChoice />,
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
        action: <PointToPage statement={key} />,
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
            {b.action ? <div className="mt-3">{b.action}</div> : null}
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


const TYPES = [
  { value: "corporate", label: "Corporate" },
  { value: "bank", label: "Bank" },
  { value: "nhs_trust", label: "NHS trust" },
  { value: "other", label: "Other" },
];

/** "Corporate / Bank / NHS trust / Other" with a reason; ratios re-run under that type. */
function DocumentTypeChoice() {
  const { report, reload } = useReportContext();
  const [choice, setChoice] = React.useState<string | null>(null);
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!choice || !reason.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await decisions.documentType(report.id, { document_type: choice, reason: reason.trim() });
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-2" data-testid="document-type-form">
      <div role="radiogroup" aria-label="Document type" className="flex flex-wrap gap-1.5">
        {TYPES.map((t) => (
          <label
            key={t.value}
            className={cn(
              "cursor-pointer rounded-full border px-3 py-1 text-[12.5px] font-medium transition-colors",
              choice === t.value ? "border-ink bg-ink text-ink-inverse" : "border-line-strong bg-surface text-ink-2 hover:text-ink",
            )}
          >
            <input
              type="radio"
              name="document-type"
              value={t.value}
              className="sr-only"
              checked={choice === t.value}
              onChange={() => setChoice(t.value)}
              data-testid={`document-type-${t.value}`}
            />
            {t.label}
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="document-type-reason" className="sr-only">
          Reason
        </label>
        <input
          id="document-type-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why (kept in the audit trail)"
          className="h-8 min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-2 text-[13px] text-ink"
          data-testid="document-type-reason"
        />
        <Button type="submit" size="sm" disabled={busy || !choice || !reason.trim()} data-testid="document-type-submit">
          {busy ? "Saving…" : "Confirm type"}
        </Button>
      </div>
      {error ? <p role="alert" className="text-[12.5px] text-missing">{error}</p> : null}
    </form>
  );
}

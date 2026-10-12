"use client";

import { Lock } from "lucide-react";
import * as React from "react";
import { useReportContext } from "@/components/report/context";
import { PdfViewer } from "@/components/report/pdf-viewer";
import { Button } from "@/components/ui/button";
import { ApiError, decisions } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { markProcessing, useDecision } from "@/lib/queries";

const CURRENCIES = [
  { code: "GBP", label: "Pounds sterling (£)" },
  { code: "EUR", label: "Euro (€)" },
  { code: "USD", label: "US dollars ($)" },
];
const SCALES = [
  { value: 1, label: "Units (as printed)" },
  { value: 1000, label: "Thousands (£000, £k)" },
  { value: 1_000_000, label: "Millions (£m)" },
  { value: 1_000_000_000, label: "Billions (£bn)" },
];

/**
 * Needs unit confirmation (UI.md section 3): a blocking dialog. The person reads the unit off the
 * page in the viewer; the page on screen is recorded as the evidence page. Nothing else is shown
 * until it is confirmed, and the pack carries a permanent "Unit confirmed manually" badge.
 */
export function UnitDialog() {
  const { report } = useReportContext();
  const decide = useDecision(report.id);
  const toast = useToast();
  const [currency, setCurrency] = React.useState("GBP");
  const [scale, setScale] = React.useState<number | null>(null);
  const [page, setPage] = React.useState(Math.min(2, report.page_count));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const first = React.useRef<HTMLSelectElement>(null);
  React.useEffect(() => first.current?.focus(), []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (scale === null) return;
    setBusy(true);
    setError(null);
    try {
      await decide(() => decisions.unit(report.id, { currency, unit_scale: scale, evidence_page: page }), markProcessing());
    } catch (err) {
      const message = err instanceof ApiError ? err.message : String(err);
      setError(message);
      toast({ tone: "error", title: "The unit wasn’t confirmed", body: message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-[2px]">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="unit-title"
        data-testid="unit-dialog"
        className="grid max-h-[92vh] w-full max-w-5xl grid-cols-1 overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-pop)] md:grid-cols-[minmax(0,1fr)_340px]"
      >
        <div className="min-h-0 overflow-auto border-b border-line md:border-b-0 md:border-r">
          <PdfViewer
            url={`/api/reports/${report.id}/original`}
            page={page}
            highlights={NO_HIGHLIGHTS}
            folio={() => null}
            onPageChange={setPage}
          />
        </div>
        <form onSubmit={submit} className="flex flex-col gap-4 p-5">
          <div>
            <span className="inline-flex size-8 items-center justify-center rounded-lg bg-review-soft">
              <Lock aria-hidden className="size-4 text-review" />
            </span>
            <h2 id="unit-title" className="mt-2 text-[1rem] font-semibold text-ink">
              Confirm the unit and currency
            </h2>
            <p className="mt-1 text-[0.78125rem] leading-relaxed text-ink-2">
              No unit was found in the statement headers, so no figure is shown. Read it off the page
              (for example “£m” or “£000” above the figures column) and confirm it here.
            </p>
          </div>
          <label className="space-y-1 text-[0.78125rem] font-medium text-ink-2">
            Currency
            <select
              ref={first}
              data-testid="unit-currency"
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              className="mt-1 h-9 w-full rounded-md border border-line-strong bg-surface px-2 text-[0.8125rem] text-ink"
            >
              {CURRENCIES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="space-y-1.5">
            <legend className="text-[0.78125rem] font-medium text-ink-2">Figures are in</legend>
            {SCALES.map((s) => (
              <label key={s.value} className="flex items-center gap-2 text-[0.8125rem] text-ink">
                <input
                  type="radio"
                  name="unit-scale"
                  value={s.value}
                  checked={scale === s.value}
                  onChange={() => setScale(s.value)}
                  data-testid={`unit-scale-${s.value}`}
                />
                {s.label}
              </label>
            ))}
          </fieldset>
          <p className="text-[0.78125rem] text-ink-2" data-testid="unit-evidence">
            Evidence page: <span className="num font-medium text-ink">PDF p.&nbsp;{page}</span>, the page on screen.
          </p>
          {error ? (
            <p role="alert" className="rounded-md border border-missing-line bg-missing-soft px-3 py-2 text-[0.78125rem] text-missing">
              {error}
            </p>
          ) : null}
          <div className="mt-auto flex justify-end">
            <Button type="submit" disabled={busy || scale === null} data-testid="unit-confirm">
              {busy ? "Confirming…" : "Confirm unit"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

const NO_HIGHLIGHTS: never[] = [];

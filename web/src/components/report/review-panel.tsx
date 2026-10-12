"use client";

import { Bot, CircleAlert, FileSearch, PenLine } from "lucide-react";
import * as React from "react";
import { PageChip } from "@/components/report/chips";
import { useReportContext } from "@/components/report/context";
import { Button } from "@/components/ui/button";
import { ApiError, decisions } from "@/lib/api";
import { cn } from "@/lib/cn";
import { warningSentence } from "@/lib/copy";
import { FAMILY_NAMES, itemLabel, STATEMENT_NAMES } from "@/lib/items";
import { type CellInfo, cellInfo } from "@/lib/states";
import { useToast } from "@/components/ui/toast";
import { markProcessing, useDecision } from "@/lib/queries";

/** The states in which a figure is waiting for a person (UI.md section 6.3). */
const NEEDS_DECISION = new Set(["R6", "R7", "R8"]);

/**
 * Review actions (UI.md 6.3), shown only when the selected figure needs a decision. Every action
 * goes to the API, which checks it (the anchor test, the value against its printed text) and
 * re-runs what depends on it. Nothing here produces a number: the person types what is printed.
 */
export function ReviewPanel({ item, period }: { item: string; period: string }) {
  const { report, review } = useReportContext();
  const info = cellInfo(report, review?.items ?? [], item, period);
  const [form, setForm] = React.useState<{ page: string; raw: string } | null>(null);
  if (!NEEDS_DECISION.has(info.state) || report.status === "needs_unit_confirmation") return null;
  const accepted = acceptable(review?.items ?? [], item, period);
  return (
    <section
      aria-labelledby="review-heading"
      data-testid="review-panel"
      className="hidden space-y-4 border-t border-line px-5 py-4 md:block"
    >
      <h4 id="review-heading" className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">
        Your decision
      </h4>

      {accepted.length ? (
        <AcceptCandidates item={item} period={period} candidates={accepted} />
      ) : null}

      {info.state === "R6" && !accepted.length && info.candidate?.raw_text ? (
        <Withheld info={info} onUse={(page, raw) => setForm({ page, raw })} />
      ) : null}

      {info.state === "R7" && info.suggestion ? (
        <div className="rounded-lg border border-suggested-line bg-suggested-soft/60 px-3 py-2.5 text-[12.5px] text-ink-2" data-testid="review-suggestion">
          <p className="flex items-center gap-1.5 font-medium text-suggested">
            <Bot aria-hidden className="size-4" /> Suggested by model
          </p>
          <p className="mt-1 leading-relaxed">
            The model points at the row “{info.suggestion.label}”
            {info.suggestion.page ? ` on p. ${info.suggestion.page}` : ""}. It never supplies a
            figure: to confirm, enter the figure printed on that row.
          </p>
          <Button
            size="sm"
            variant="outline"
            className="mt-2"
            data-testid="confirm-suggestion"
            onClick={() => setForm({ page: String(info.suggestion?.page ?? ""), raw: "" })}
          >
            Confirm from the page
          </Button>
        </div>
      ) : null}

      <EnterFromPage key={`${item}-${period}-${form?.page}-${form?.raw}`} item={item} period={period} initial={form} />
      {info.state === "R8" ? <PointToPage statement={statementOf(report, item)} /> : null}
      <LeaveEmpty item={item} period={period} />
    </section>
  );
}

// ------------------------------------------------------------------------------ candidates

interface ValueCandidate {
  id: string;
  value: number;
  raw_text: string;
  page: number;
  /** Who read it: engine families from extraction, or an engine name. */
  source: string | null;
}

/** Candidates the API can accept: review rows whose candidates carry a printed value. */
function acceptable(
  items: { id: number; item: string | null; period_id: string | null; candidates: Record<string, unknown>[] }[],
  item: string,
  period: string,
): ValueCandidate[] {
  const out: ValueCandidate[] = [];
  for (const r of items) {
    if (r.item !== item || (r.period_id !== null && r.period_id !== period)) continue;
    r.candidates.forEach((c, i) => {
      if (typeof c.value === "number" && typeof c.raw_text === "string" && typeof c.page === "number") {
        const families = Array.isArray(c.families) ? (c.families as string[]) : [];
        const source = families.length
          ? families.map((f) => FAMILY_NAMES[f] ?? f).join(" and ")
          : typeof c.engine === "string"
            ? c.engine
            : null;
        out.push({ id: `${r.id}:${i}`, value: c.value, raw_text: c.raw_text, page: c.page, source });
      }
    });
  }
  return out;
}

function AcceptCandidates({ item, period, candidates }: { item: string; period: string; candidates: ValueCandidate[] }) {
  const { report, reload, select } = useReportContext();
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const use = async (c: ValueCandidate) => {
    setBusy(c.id);
    setError(null);
    try {
      await decisions.override(report.id, { action: "accept_candidate", item, period_id: period, candidate_id: c.id });
      await reload();
      select({ kind: "figure", item, period });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="space-y-2" data-testid="review-candidates">
      <p className="text-[12.5px] text-ink-2">
        {candidates.length > 1 ? "The engines read different figures. Choose the one printed on the page:" : "The figure read from the page, withheld for review:"}
      </p>
      <ul className="space-y-1.5">
        {candidates.map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2">
            <span className="flex items-center gap-2 text-[13px]">
              <span className="num font-mono text-ink">{c.raw_text}</span>
              <PageChip page={c.page} />
              {c.source ? <span className="text-[11.5px] text-ink-3">{c.source}</span> : null}
            </span>
            <Button size="sm" onClick={() => use(c)} disabled={busy !== null} data-testid="use-candidate">
              {busy === c.id ? "Saving…" : "Use this"}
            </Button>
          </li>
        ))}
      </ul>
      {error ? <Refusal text={error} /> : null}
    </div>
  );
}

/** R6 whose candidate exists only in the extraction report: shown, and offered to the form. */
function Withheld({ info, onUse }: { info: CellInfo; onUse: (page: string, raw: string) => void }) {
  const c = info.candidate!;
  return (
    <div className="rounded-lg border border-review-line bg-review-soft/50 px-3 py-2.5 text-[12.5px] text-ink-2" data-testid="review-withheld">
      <p className="flex items-center gap-1.5 font-medium text-review">
        <CircleAlert aria-hidden className="size-4" /> Withheld candidate
      </p>
      <p className="mt-1 flex flex-wrap items-center gap-1.5">
        <span className="num font-mono text-ink">{c.raw_text}</span>
        {c.page ? <span>on p.&nbsp;{c.page}</span> : null}
        {c.families?.length ? <span className="text-ink-3">· {c.families.map((f) => FAMILY_NAMES[f] ?? f).join(" and ")}</span> : null}
      </p>
      {info.warnings.length ? <p className="mt-1">{warningSentence(info.warnings[0]!)}</p> : null}
      <Button
        size="sm"
        variant="outline"
        className="mt-2"
        data-testid="use-withheld"
        onClick={() => onUse(c.page ? String(c.page) : "", c.raw_text ?? "")}
      >
        Enter this figure
      </Button>
    </div>
  );
}

// ------------------------------------------------------------------------------ enter from a page

function EnterFromPage({ item, period, initial }: { item: string; period: string; initial: { page: string; raw: string } | null }) {
  const { report, reload, select } = useReportContext();
  const [page, setPage] = React.useState(initial?.page ?? "");
  const [raw, setRaw] = React.useState(initial?.raw ?? "");
  const [value, setValue] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [forcing, setForcing] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [open, setOpen] = React.useState(initial !== null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const n = Number(page);
    const v = Number(value);
    if (!Number.isInteger(n) || n < 1 || !raw.trim() || value.trim() === "" || Number.isNaN(v)) {
      setRefusal("Enter the page number, the figure as printed and its value.");
      return;
    }
    setBusy(true);
    setRefusal(null);
    try {
      await decisions.override(report.id, {
        action: "set_value", item, period_id: period, value: v, raw_text: raw.trim(), page: n,
        ...(forcing ? { force: true, reason: reason.trim() } : {}),
      });
      await reload();
      select({ kind: "figure", item, period });
    } catch (err) {
      if (err instanceof ApiError && err.code === "unanchored_override") {
        setRefusal(`That text isn’t on page ${n}. Check the page number or select the figure on the page.`);
      } else if (err instanceof ApiError && err.code === "reason_required") {
        setRefusal("A figure that isn’t printed on the page can only be forced with a reason.");
      } else {
        setRefusal(err instanceof ApiError ? err.message : String(err));
      }
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="enter-from-page">
        <PenLine aria-hidden /> Enter from a page
      </Button>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-2.5 rounded-lg border border-line px-3 py-3" data-testid="enter-form" aria-label={`Enter ${itemLabel(item)} ${period} from a page`}>
      <p className="text-[12.5px] font-medium text-ink">Enter {itemLabel(item).toLowerCase()} for {period} from a page</p>
      <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-2">
        <Field label="Page" id="enter-page">
          <input id="enter-page" inputMode="numeric" value={page} onChange={(e) => setPage(e.target.value)} className={INPUT} data-testid="enter-page" />
        </Field>
        <Field label="As printed" id="enter-raw">
          <input id="enter-raw" value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="e.g. (3,300)" className={cn(INPUT, "font-mono")} data-testid="enter-raw" />
        </Field>
      </div>
      <Field label={`Value in the pack’s unit (liabilities as positive amounts)`} id="enter-value">
        <input id="enter-value" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} className={cn(INPUT, "num")} data-testid="enter-value" />
      </Field>
      <label className="flex items-center gap-2 text-[12.5px] text-ink-2">
        <input type="checkbox" checked={forcing} onChange={(e) => setForcing(e.target.checked)} data-testid="enter-force" />
        It isn’t printed on the page: force it, with a reason
      </label>
      {forcing ? (
        <Field label="Reason (kept with the figure for good)" id="enter-reason">
          <textarea id="enter-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={cn(INPUT, "h-auto py-1.5")} data-testid="enter-reason" />
        </Field>
      ) : null}
      {refusal ? <Refusal text={refusal} /> : null}
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={busy} data-testid="enter-submit">
          {busy ? "Checking…" : "Save figure"}
        </Button>
      </div>
    </form>
  );
}

// ------------------------------------------------------------------------------ the rest

function statementOf(report: ReturnType<typeof useReportContext>["report"], item: string): string {
  return report.extraction?.searched_for?.[item]?.statement ?? report.pack?.items[item]?.statement ?? "balance_sheet";
}

/** Re-run extraction for a statement on the page a person names (EXTRACTION section 6). */
export function PointToPage({ statement }: { statement: string }) {
  const { report } = useReportContext();
  const decide = useDecision(report.id);
  const toast = useToast();
  const [page, setPage] = React.useState(String(report.extraction?.statements?.[statement]?.pages?.[0] ?? ""));
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await decide(
        () => decisions.statementLocation(report.id, { statement_type: statement, page: Number(page) }),
        markProcessing(),
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : String(err);
      setError(message);
      toast({ tone: "error", title: "Extraction didn’t run again", body: message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-2 rounded-lg border border-line px-3 py-3" data-testid="point-to-page">
      <p className="flex items-center gap-1.5 text-[12.5px] font-medium text-ink">
        <FileSearch aria-hidden className="size-4 text-ink-3" />
        Point to the {STATEMENT_NAMES[statement] ?? statement.replace(/_/g, " ")}
      </p>
      <p className="text-[12px] leading-relaxed text-ink-3">Extraction runs again on that page; the figures and ratios follow.</p>
      <div className="flex items-end gap-2">
        <Field label="Page" id="point-page">
          <input id="point-page" inputMode="numeric" value={page} onChange={(e) => setPage(e.target.value)} className={cn(INPUT, "w-24")} data-testid="point-page" />
        </Field>
        <Button type="submit" size="sm" variant="outline" disabled={busy || !/^\d+$/.test(page)} data-testid="point-submit">
          {busy ? "Re-reading…" : "Read this page"}
        </Button>
      </div>
      {error ? <Refusal text={error} /> : null}
    </form>
  );
}

function LeaveEmpty({ item, period }: { item: string; period: string }) {
  const { report, reload } = useReportContext();
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-[12px] text-ink-3 underline-offset-2 hover:text-ink hover:underline">
        Leave it empty, with a reason
      </button>
    );
  }
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await decisions.override(report.id, { action: "set_null", item, period_id: period, reason: reason.trim() });
      await reload();
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };
  return (
    <form onSubmit={submit} className="space-y-2 rounded-lg border border-line px-3 py-3" data-testid="leave-empty">
      <Field label="Why it stays empty" id="null-reason">
        <textarea id="null-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={cn(INPUT, "h-auto py-1.5")} />
      </Field>
      {error ? <Refusal text={error} /> : null}
      <div className="flex justify-end">
        <Button type="submit" size="sm" variant="outline" disabled={!reason.trim()}>
          Record it
        </Button>
      </div>
    </form>
  );
}

const INPUT = "h-8 w-full rounded-md border border-line-strong bg-surface px-2 text-[13px] text-ink";

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-[11.5px] font-medium text-ink-3">
        {label}
      </label>
      {children}
    </div>
  );
}

function Refusal({ text }: { text: string }) {
  return (
    <p role="alert" data-testid="review-refusal" className="rounded-md border border-missing-line bg-missing-soft px-3 py-2 text-[12.5px] leading-relaxed text-missing">
      {text}
    </p>
  );
}

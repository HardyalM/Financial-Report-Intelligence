/**
 * Row states (UI.md section 4) and ratio-card states (section 5), derived from what the API
 * returned. Nothing here computes a number: it classifies values the pipeline published.
 */
import type {
  Candidate,
  PackWarning,
  PeriodValue,
  Ratio,
  Report,
  ReviewItem,
  StatementPack,
} from "@/lib/types";

export type RowState = "R1" | "R2" | "R3" | "R4" | "R5" | "R6" | "R7" | "R8" | "R9" | "R10";
export type CardState = "K1" | "K2" | "K3" | "K4" | "K5";

/** Items a warning says are null by design (EXTRACTION section 1.4). */
const NOT_APPLICABLE_BY: Record<string, string[]> = {
  bank_layout: ["revenue", "current_assets", "current_liabilities"],
  unclassified_balance_sheet: ["current_assets", "current_liabilities"],
};

const NOT_APPLICABLE_REASON: Record<string, string> = {
  unclassified_balance_sheet: "the balance sheet has no current/non-current split",
  bank_layout: "banks report net interest and fee income, not revenue",
};

const UNRESOLVED_DECISIONS = new Set(["below_threshold", "disagreement", "review", "withheld"]);

export interface CellInfo {
  state: RowState;
  value: PeriodValue | null;
  candidate: Candidate | null;
  /** For R6: the deterministic candidates waiting for a person. */
  candidates: Candidate[];
  /** For R7: the model's pointer (a row label, never a number). */
  suggestion: { label: string; reason: string | null; page: number | null } | null;
  /** For R9: why the line does not apply. */
  notApplicable: string | null;
  warnings: PackWarning[];
}

export function candidateFor(report: Report, item: string, period: string): Candidate | null {
  return report.extraction?.candidates?.[`${item}:${period}`] ?? null;
}

function notApplicable(pack: StatementPack, item: string): string | null {
  for (const w of pack.warnings) {
    if (NOT_APPLICABLE_BY[w.code]?.includes(item)) {
      return NOT_APPLICABLE_REASON[w.code] ?? "this line does not apply to this kind of report";
    }
  }
  if (pack.balance_sheet_classified === false && NOT_APPLICABLE_BY.unclassified_balance_sheet!.includes(item)) {
    return NOT_APPLICABLE_REASON.unclassified_balance_sheet!;
  }
  return null;
}

export function suggestionFor(review: ReviewItem[], item: string, period: string): CellInfo["suggestion"] {
  const hit = review.find(
    (r) => r.kind === "llm_suggestion" && r.item === item && (r.period_id == null || r.period_id === period),
  );
  const c = hit?.candidates[0] as { label?: string; reason?: string; page?: number } | undefined;
  return hit && c?.label ? { label: c.label, reason: c.reason ?? null, page: c.page ?? null } : null;
}

export function itemWarnings(pack: StatementPack, item: string): PackWarning[] {
  return pack.warnings.filter((w) => w.item === item);
}

/** The state of one figure: one item in one period. */
export function cellInfo(report: Report, review: ReviewItem[], item: string, period: string): CellInfo {
  const pack = report.pack;
  const base = {
    candidate: candidateFor(report, item, period),
    candidates: [] as Candidate[],
    suggestion: null,
    notApplicable: null,
  };
  if (!pack) return { ...base, state: "R10", value: null, warnings: [] };
  const value = pack.items[item]?.values.find((v) => v.period_id === period) ?? null;
  const warnings = itemWarnings(pack, item);
  if (value && value.value !== null) {
    const families = base.candidate?.families ?? [];
    let state: RowState = "R2";
    if (value.engine === "human_override_unanchored") state = "R5";
    else if (value.engine === "human_override") state = "R4";
    else if (value.engine === "derived" || (value.derived_from?.length ?? 0) > 0) state = "R3";
    else if (value.engine === "reconciled" || families.length >= 2) state = "R1";
    return { ...base, state, value, warnings };
  }
  const na = notApplicable(pack, item);
  if (na) return { ...base, state: "R9", value, notApplicable: na, warnings };
  const disputed = warnings.filter((w) => w.code === "parser_disagreement");
  const c = base.candidate;
  if ((c && c.raw_text && UNRESOLVED_DECISIONS.has(c.decision ?? "")) || disputed.length) {
    const candidates = c && c.raw_text ? [c] : [];
    return { ...base, state: "R6", value, candidates, warnings };
  }
  const suggestion = suggestionFor(review, item, period);
  if (suggestion) return { ...base, state: "R7", value, suggestion, warnings };
  return { ...base, state: "R8", value, warnings };
}

export const ROW_STATE_LABEL: Record<RowState, string> = {
  R1: "Two engine families agree",
  R2: "One engine family",
  R3: "Derived",
  R4: "Confirmed by you",
  R5: "Manual: not found on page",
  R6: "Needs review",
  R7: "Suggested by model",
  R8: "Not found",
  R9: "Not applicable",
  R10: "Blocked",
};

// ------------------------------------------------------------------------------------- ratios

export interface CardInfo {
  state: CardState;
  /** K6 is shown on top of K1 or K2: an input a person entered, forced or confirmed. */
  manual: boolean;
  /** K2: the value is shown, with this beside it. */
  flag: string | null;
  /** K5: what the ratios are waiting for. */
  withheldFor?: "unit" | "document_type";
}

export function cardInfo(report: Report, ratio: Ratio | null): CardInfo {
  if (report.status === "needs_unit_confirmation") {
    return { state: "K5", manual: false, flag: null, withheldFor: "unit" };
  }
  if (!ratio || report.status === "needs_document_type" || ratio.status === "withheld") {
    return { state: "K5", manual: false, flag: null, withheldFor: "document_type" };
  }
  if (ratio.status === "not_applicable") return { state: "K4", manual: false, flag: null };
  if (ratio.value === null) return { state: "K3", manual: false, flag: null };
  const manual = Object.values(ratio.inputs).some((i) =>
    i.badges.some((b) => b === "manual" || b === "manual_unanchored"),
  );
  if (ratio.flags.includes("negative_denominator")) {
    const what = ratio.name === "debt_to_equity" ? "negative equity" : "negative denominator";
    return { state: "K2", manual, flag: `Not meaningful: ${what}` };
  }
  return { state: "K1", manual, flag: null };
}

/** "needs review", "suggested by model", "not found": how a missing input is described. */
export function missingPhrase(state: RowState): string {
  switch (state) {
    case "R6":
      return "needs review";
    case "R7":
      return "suggested by model, not confirmed";
    case "R9":
      return "not applicable";
    case "R10":
      return "unit not confirmed";
    default:
      return "not found";
  }
}

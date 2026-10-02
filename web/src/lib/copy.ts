/**
 * Warning codes in words (UI.md section 4: "Warning codes are always translated into a sentence.
 * The code itself is shown only on hover"). UK English, neutral verbs.
 */
import type { PackWarning } from "@/lib/types";
import { itemLabel } from "@/lib/items";

const CHECKS: Record<string, string> = {
  current_assets_section_sum: "The current-asset lines don’t add up to the subtotal",
  current_liabilities_section_sum: "The current-liability lines don’t add up to the subtotal",
  non_current_assets_section_sum: "The non-current asset lines don’t add up to the subtotal",
  profit_before_tax_chain: "Operating profit and the lines below it don’t add up to profit before tax",
  net_income_chain: "Profit before tax less tax doesn’t equal profit for the year",
  total_equity_components: "The equity lines don’t add up to total equity",
  balance_sheet_identity: "Total assets don’t equal total liabilities plus equity",
};

/** "current_assets_section_sum for FY2025: 2 rows above; off by 750 (tolerance 1.5)" in words. */
export function checkSentence(message: string): string {
  const name = message.split(/[\s:]/, 1)[0] ?? "";
  const period = /\bfor (\S+?):/.exec(message)?.[1];
  const off = /off by (-?[\d,.]+)/.exec(message)?.[1];
  const head = CHECKS[name] ?? "An arithmetic check on the statement failed";
  const parts = [off ? `off by ${off.replace(/^-/, "")}` : null, period ? `in ${period}` : null].filter(Boolean);
  return parts.length ? `${head} (${parts.join(" ")}).` : `${head}.`;
}

export function warningSentence(w: PackWarning): string {
  const item = w.item ? itemLabel(w.item) : null;
  const page = w.page ? `p. ${w.page}` : null;
  switch (w.code) {
    case "missing_item":
      if (w.message.includes("null by design for a bank: ")) {
        const why = w.message.split("null by design for a bank: ")[1] ?? "";
        return `Not applicable to a bank: ${why}.`;
      }
      if (/no alias map for document type (\w+)/.test(w.message)) {
        const kind = /document type (\w+)/.exec(w.message)?.[1] ?? "this";
        return `Not extracted: there is no line-item map for ${kind === "bank" ? "bank" : kind} accounts yet.`;
      }
      if (w.item === "total_debt" && w.message.includes("Financial liabilities")) {
        return "The balance sheet shows only ‘Financial liabilities’, which include derivatives and other items, so interest-bearing borrowings can’t be separated out. Total debt is left empty rather than estimated.";
      }
      if (w.item === "total_debt") {
        return "No borrowings or lease liabilities lines were found to build total debt from.";
      }
      return `${item ?? "This line"} was not found${/for (FY\S+)/.test(w.message) ? ` for ${/for (FY\S+)/.exec(w.message)?.[1]}` : ""}.`;
    case "low_confidence":
      return "The best reading scored below the publication threshold, so it is held for review.";
    case "arithmetic_check_failed":
      return checkSentence(w.message);
    case "parser_disagreement":
      return w.message.startsWith("resolved")
        ? `The two engine families read different figures${page ? ` on ${page}` : ""}; the figure printed on the page was kept.`
        : `The two engine families read different figures${page ? ` on ${page}` : ""}.`;
    case "derived_value":
      return `${item ?? "This figure"} is derived in code from printed lines.`;
    case "human_override":
      return `Set by a person${page ? ` from ${page}` : ""}.`;
    case "human_override_unanchored": {
      const reason = w.message.split(" by a person: ")[1];
      return `Entered by a person; the figure is not printed${page ? ` on ${page}` : ""}.${reason ? ` Reason given: “${reason}”` : ""}`;
    }
    case "unit_confirmed_manually":
      return "The unit and currency were confirmed by a person.";
    case "unclassified_balance_sheet":
      return "The balance sheet has no current/non-current split, so current assets and current liabilities don’t apply.";
    case "bank_layout":
      return "A bank layout: revenue, current assets and current liabilities don’t apply.";
    case "public_sector_layout":
      return "A public-sector layout: some corporate lines don’t apply.";
    case "document_type_ambiguous":
      return "The document type is unclear, so ratios are withheld until it is confirmed.";
    case "reduced_verification":
      return "Only one engine family read the statements, so figures are checked by arithmetic but not cross-read.";
    case "not_digitally_born":
      return "This PDF has little or no text layer, so figures are suggestions for review only.";
    case "lease_not_separately_presented":
      return "Lease liabilities aren’t shown separately, so total debt is borrowings only.";
    case "sign_ambiguous":
      return "The sign of this figure is uncertain.";
    case "alias_weak":
      return "Only a weak label match was found.";
    case "period_ambiguous":
      return "The reporting period of a column couldn’t be identified.";
    case "entity_scope_ambiguous":
      return "It isn’t clear whether this statement is the group’s or the parent company’s.";
    case "restated_comparative":
      return "The comparative figures are restated.";
    case "multi_page_table":
      return "The statement spans more than one page.";
    case "unit_ambiguous":
    case "currency_ambiguous":
      return "The unit or currency couldn’t be read from the statement headers.";
    default:
      return "See the extraction report for details.";
  }
}

export const DECISION_SENTENCES: Record<string, string> = {
  financial_liabilities_not_isolable:
    "The balance sheet shows only ‘Financial liabilities’, which include derivatives, so borrowings can’t be separated out.",
  blocked: "Extraction is blocked until the unit is confirmed.",
};

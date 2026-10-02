/** Canonical line items as the figures table shows them (docs/SCHEMA.md section 5). */

export interface ItemDef {
  id: string;
  label: string;
  group: "income" | "balance" | "equity" | "debt";
  /** A locked ratio input (CLAUDE.md). */
  ratioInput?: boolean;
}

export const ITEMS: ItemDef[] = [
  { id: "revenue", label: "Revenue", group: "income", ratioInput: true },
  { id: "operating_profit", label: "Operating profit", group: "income", ratioInput: true },
  { id: "profit_before_tax", label: "Profit before tax", group: "income" },
  { id: "net_income", label: "Profit for the year", group: "income" },
  { id: "non_current_assets", label: "Non-current assets", group: "balance" },
  { id: "current_assets", label: "Current assets", group: "balance", ratioInput: true },
  { id: "cash", label: "Cash and cash equivalents", group: "balance" },
  { id: "total_assets", label: "Total assets", group: "balance", ratioInput: true },
  { id: "current_liabilities", label: "Current liabilities", group: "balance", ratioInput: true },
  { id: "total_liabilities", label: "Total liabilities", group: "balance" },
  { id: "equity_attributable_to_owners", label: "Equity attributable to owners", group: "equity" },
  { id: "non_controlling_interests", label: "Non-controlling interests", group: "equity" },
  { id: "total_equity", label: "Total equity", group: "equity", ratioInput: true },
  { id: "total_debt", label: "Total debt", group: "debt", ratioInput: true },
  { id: "financial_liabilities_current", label: "Financial liabilities (current)", group: "debt" },
  { id: "financial_liabilities_non_current", label: "Financial liabilities (non-current)", group: "debt" },
];

/** Shown under `total_debt` (its components), not as rows of their own. */
export const DEBT_COMPONENTS: Record<string, string> = {
  borrowings_current: "Borrowings (current)",
  borrowings_non_current: "Borrowings (non-current)",
  lease_liabilities_current: "Lease liabilities (current)",
  lease_liabilities_non_current: "Lease liabilities (non-current)",
};

export const GROUP_TITLES: Record<ItemDef["group"], string> = {
  income: "Income statement",
  balance: "Balance sheet",
  equity: "Equity",
  debt: "Debt",
};

const BY_ID = new Map(ITEMS.map((i) => [i.id, i]));

export function itemLabel(id: string): string {
  return BY_ID.get(id)?.label ?? DEBT_COMPONENTS[id] ?? humanise(id);
}

export function humanise(id: string): string {
  const words = id.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Items in table order: known items first, then anything else the pack carries. */
export function orderedItems(ids: string[]): ItemDef[] {
  const present = new Set(ids);
  const known = ITEMS.filter((i) => present.has(i.id));
  const extra = ids
    .filter((id) => !BY_ID.has(id) && !(id in DEBT_COMPONENTS))
    .sort()
    .map((id): ItemDef => ({ id, label: humanise(id), group: "balance" }));
  return [...known, ...extra];
}

export const STATEMENT_NAMES: Record<string, string> = {
  income_statement: "consolidated income statement",
  balance_sheet: "consolidated balance sheet",
  comprehensive_income: "statement of comprehensive income",
  cash_flow: "cash flow statement",
  changes_in_equity: "statement of changes in equity",
};

export const DOCUMENT_TYPES: Record<string, string> = {
  corporate: "Corporate",
  bank: "Bank",
  nhs_trust: "NHS trust",
  other: "Other",
};

export const FAMILY_NAMES: Record<string, string> = {
  text_layer: "text layer",
  image_layout: "image layout",
  ocr: "OCR",
};

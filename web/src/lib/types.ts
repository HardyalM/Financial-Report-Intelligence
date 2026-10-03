/**
 * The API's shapes. Envelopes come from schemas/openapi.json; the pack, ratio pack and commentary
 * from their own JSON Schemas (all generated: npm run types). The extraction view is typed here
 * because the API declares it as an object (finintel/api/extraction_view.py).
 */
import type { components } from "@/types/generated/api";
import type {
  Citation,
  Commentary as CommentaryOutput,
  Figure,
  Paragraph,
  Summary,
  Topic,
} from "@/types/generated/commentary";
import type {
  PeriodChange,
  PeriodRatios,
  Ratio,
  RatioInput,
  RatioPack,
} from "@/types/generated/ratio-pack";
import type {
  DerivedComponent,
  LineItem,
  PackWarning,
  Period,
  PeriodValue,
  StatementPack,
} from "@/types/generated/statement-pack";

export type {
  Citation, CommentaryOutput, DerivedComponent, Figure, LineItem, PackWarning, Paragraph, Period,
  PeriodChange, PeriodRatios, PeriodValue, Ratio, RatioInput, RatioPack, StatementPack, Summary,
  Topic,
};
export type RatioName = keyof PeriodRatios["ratios"];
export type { ReportedMetric } from "@/types/generated/reported-metric";

type Schemas = components["schemas"];
export type Job = Schemas["JobOut"];
export type ReviewItem = Schemas["ReviewItemOut"];

export interface Candidate {
  decision?: string;
  families?: string[];
  engines?: string[];
  label?: string;
  raw_text?: string;
  page?: number;
  row?: string;
  method?: string;
  confidence?: number;
  checks_passed?: string[];
  checks_failed?: string[];
  components_found?: Record<string, boolean>;
}

export interface StatementLocation {
  statement_type: string;
  status: "found" | "not_found" | string;
  pages: number[];
  page_labels: string[];
  title: string | null;
  scope: string | null;
}

export interface ArithmeticCheck {
  engine: string;
  name: string;
  period: string;
  passed: boolean;
  difference: string;
  tolerance: string;
  detail: string;
}

export interface SearchedFor {
  statement: string;
  pages: number[];
  labels: string[];
  components: string[];
  warnings: PackWarning[];
}

export interface ExtractionView {
  /** printed folio = PDF page − folio_offset, when the locator could infer it. */
  folio_offset?: number | null;
  statements: Record<string, StatementLocation>;
  statement_names: Record<string, string>;
  candidates: Record<string, Candidate>;
  checks: ArithmeticCheck[];
  engines: string[];
  engine_skipped: Record<string, string>;
  families: string[];
  searched_for: Record<string, SearchedFor>;
}

export type Report = Omit<Schemas["ReportOut"], "pack" | "ratios" | "extraction"> & {
  pack: StatementPack | null;
  ratios: RatioPack | null;
  extraction?: ExtractionView | null;
};

export interface NumbersSnapshot {
  period_id: string;
  rendered: string;
  template: string;
}

export type CommentaryResponse = Omit<Schemas["CommentaryOut"], "output" | "validation"> & {
  output: CommentaryOutput;
  validation: { snapshot?: NumbersSnapshot; audit?: unknown; pre_validation?: unknown };
};

export type Review = Omit<Schemas["ReviewOut"], "warnings"> & { warnings: PackWarning[] };

export interface ReportedMetrics {
  metrics: import("@/types/generated/reported-metric").ReportedMetric[];
  notes: string[];
}

/**
 * Number formatting. The UI formats figures that the pipeline computed; it never computes a
 * figure itself (CLAUDE.md). Ratio values and changes mirror finintel/commentary/render so the
 * cards and the commentary agree to the character: 15.5%, 0.76x, +0.4 pp, -1.20x.
 */

const MINUS = "−";

/** value × 10^n on the decimal string (no binary error), as Decimal(str(value)) would shift. */
function shift(value: number, n: number): number {
  const text = String(value);
  return text.includes("e") ? value * 10 ** n : Number(`${text}e${n}`);
}

/** Half-up rounding on the decimal string, as Python's Decimal.quantize(ROUND_HALF_UP) does. */
export function roundHalfUp(value: number, places: number): string {
  const sign = value < 0 ? -1 : 1;
  const shifted = shift(Math.abs(value), places);
  const rounded = Math.round(shifted);
  const out = Number(`${rounded}e-${places}`) * sign;
  const text = out.toFixed(places);
  return /^-0(\.0+)?$/.test(text) ? text.slice(1) : text;
}

const grouping = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });

/** A figure in the pack's own unit, as statements print it: 60,761 and (350) for a negative. */
export function formatFigure(value: number): string {
  const text = grouping.format(Math.abs(value));
  return value < 0 ? `(${text})` : text;
}

const SYMBOLS: Record<string, string> = { GBP: "£", EUR: "€", USD: "$" };

export function currencySymbol(currency: string | null | undefined): string {
  if (!currency) return "";
  return SYMBOLS[currency] ?? `${currency} `;
}

/** "£m", "€m", "£000", "£": how the figures column is labelled. */
export function unitLabel(currency: string | null | undefined, unitScale: number | null | undefined): string {
  const symbol = currencySymbol(currency).trim();
  switch (unitScale) {
    case 1_000_000_000:
      return `${symbol}bn`;
    case 1_000_000:
      return `${symbol}m`;
    case 1_000:
      return `${symbol}000`;
    case 1:
      return symbol || "units";
    default:
      return symbol;
  }
}

export function unitWords(unitScale: number | null | undefined): string {
  switch (unitScale) {
    case 1_000_000_000:
      return "billions";
    case 1_000_000:
      return "millions";
    case 1_000:
      return "thousands";
    case 1:
      return "units";
    default:
      return "unknown scale";
  }
}

function signed(value: number, places: number): string {
  const text = roundHalfUp(value, places);
  if (Number(text) === 0) return text.replace(/^-/, "");
  return value > 0 ? `+${text}` : `${MINUS}${text.slice(1)}`;
}

function unsignedMinus(text: string): string {
  return text.startsWith("-") ? `${MINUS}${text.slice(1)}` : text;
}

/** Fractions as a percentage to one decimal (15.5%); multiples to two decimals (1.54x). */
export function formatRatio(value: number, unit: "fraction" | "multiple"): string {
  if (unit === "fraction") return `${unsignedMinus(roundHalfUp(shift(value, 2), 1))}%`;
  return `${unsignedMinus(roundHalfUp(value, 2))}x`;
}

/** Percentage points for margins and ROCE; an absolute difference for multiples. */
export function formatRatioChange(kind: "percentage_points" | "absolute", value: number): string {
  return kind === "percentage_points" ? `${signed(value, 1)} pp` : `${signed(value, 2)}x`;
}

/** An item's change between periods, as the ratio engine computed it (ratio_pack.changes). */
export function formatPercentChange(value: number): string {
  return `${signed(value, 1)}%`;
}

const longDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

export function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : longDate.format(d);
}

export function pageRange(pages: number[]): string {
  if (pages.length === 0) return "";
  const sorted = [...new Set(pages)].sort((a, b) => a - b);
  const first = sorted[0]!;
  const last = sorted[sorted.length - 1]!;
  return first === last ? `p. ${first}` : `pp. ${first}–${last}`;
}

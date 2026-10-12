"use client";

import { CircleCheck, CircleDashed, CircleX, Loader, Lock, TriangleAlert } from "lucide-react";
import type * as React from "react";
import type { Tone } from "@/components/ui/badge";
import type { ReportSummary } from "@/lib/queries";

/** The name a report goes by: the company the pack names, else its file name. */
export function reportTitle(r: Pick<ReportSummary, "company_name" | "filename">): string {
  return r.company_name ?? r.filename.replace(/\.pdf$/i, "");
}

export interface StatusMeta {
  label: string;
  tone: Tone;
  Icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  /** A colour for the small dot beside a name (always paired with the label or an icon). */
  dot: string;
  spinning?: boolean;
}

const STATUS: Record<string, StatusMeta> = {
  ready: { label: "Ready", tone: "ok", Icon: CircleCheck, dot: "bg-ok" },
  processing: { label: "Processing", tone: "accent", Icon: Loader, dot: "bg-accent", spinning: true },
  queued: { label: "Queued", tone: "neutral", Icon: CircleDashed, dot: "bg-ink-3" },
  needs_unit_confirmation: { label: "Needs unit", tone: "review", Icon: Lock, dot: "bg-review" },
  needs_document_type: { label: "Needs document type", tone: "review", Icon: TriangleAlert, dot: "bg-review" },
  failed: { label: "Failed", tone: "missing", Icon: CircleX, dot: "bg-missing" },
};

export function statusMeta(status: string): StatusMeta {
  return STATUS[status] ?? { label: status, tone: "neutral", Icon: CircleDashed, dot: "bg-ink-3" };
}

const relative = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });
const dateOnly = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** "just now", "5 minutes ago", "yesterday", then a date. */
export function whenAdded(iso: string, now = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const s = Math.round((t - now) / 1000);
  if (Math.abs(s) < 45) return "just now";
  const m = Math.round(s / 60);
  if (Math.abs(m) < 60) return relative.format(m, "minute");
  const h = Math.round(m / 60);
  if (Math.abs(h) < 24) return relative.format(h, "hour");
  const d = Math.round(h / 24);
  if (Math.abs(d) < 7) return relative.format(d, "day");
  return dateOnly.format(t);
}

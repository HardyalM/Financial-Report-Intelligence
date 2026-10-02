"use client";

import { CircleCheck, CircleDashed, Clock, Lock, ShieldHalf, TriangleAlert, UserPen } from "lucide-react";
import { useReportContext } from "@/components/report/context";
import { Badge, type Tone } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { formatDate, unitLabel } from "@/lib/format";
import { DOCUMENT_TYPES } from "@/lib/items";

const STATUS: Record<string, { label: string; tone: Tone; Icon: typeof CircleCheck }> = {
  ready: { label: "Ready", tone: "ok", Icon: CircleCheck },
  processing: { label: "Processing", tone: "accent", Icon: Clock },
  queued: { label: "Queued", tone: "neutral", Icon: Clock },
  needs_unit_confirmation: { label: "Needs unit confirmation", tone: "review", Icon: Lock },
  needs_document_type: { label: "Needs document type", tone: "review", Icon: CircleDashed },
  failed: { label: "Failed", tone: "missing", Icon: TriangleAlert },
};

const BASIS: Record<string, string> = {
  consolidated: "Consolidated",
  company_only: "Company only",
  single_entity: "Single entity",
};

export function ReportHeader() {
  const { report, current } = useReportContext();
  const pack = report.pack;
  const name = pack?.company_name ?? report.filename.replace(/\.pdf$/i, "");
  const status = STATUS[report.status] ?? { label: report.status, tone: "neutral" as Tone, Icon: Clock };
  const unitManual = pack?.warnings.some((w) => w.code === "unit_confirmed_manually") ?? false;
  const yearEnd = formatDate(current?.end_date);

  return (
    <header className="border-b border-line bg-surface" data-testid="report-header">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-2 px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="text-[19px] font-semibold tracking-[-0.015em] text-ink" data-testid="report-title">
            {name}
          </h1>
          <span className="text-sm text-ink-3">
            {current ? `Annual report ${current.label}` : "Annual report"}
            {yearEnd ? ` · year ended ${yearEnd}` : ""}
            {pack?.basis ? ` · ${BASIS[pack.basis] ?? pack.basis}` : ""}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="neutral" data-testid="document-type-badge">
            {DOCUMENT_TYPES[report.document_type] ?? report.document_type}
          </Badge>
          {pack ? (
            <Badge tone="neutral" data-testid="unit-badge">
              <span className="num">{unitLabel(pack.currency, pack.unit_scale)}</span> {pack.currency}
            </Badge>
          ) : null}
          <Badge tone={status.tone} data-testid="status-badge">
            <status.Icon aria-hidden />
            {status.label}
          </Badge>
          {unitManual ? (
            <Tooltip content="A person confirmed the unit and currency; every figure depends on it.">
              <Badge tone="amber" tabIndex={0} data-testid="unit-confirmed-badge">
                <UserPen aria-hidden />
                Unit confirmed manually
              </Badge>
            </Tooltip>
          ) : null}
          {report.reduced_verification ? (
            <Tooltip content="Only one engine family read the statements.">
              <Badge tone="single" tabIndex={0} data-testid="reduced-verification-badge">
                <ShieldHalf aria-hidden />
                Reduced verification
              </Badge>
            </Tooltip>
          ) : null}
          <span className="ml-auto hidden font-mono text-[11px] text-ink-3 md:inline">
            {report.filename} · {report.page_count} pages
          </span>
        </div>
      </div>
    </header>
  );
}

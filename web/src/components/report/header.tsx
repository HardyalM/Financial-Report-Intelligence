"use client";

import {
  CalendarDays,
  CircleCheck,
  CircleDashed,
  Clock,
  Copy,
  FileText,
  Link2,
  Lock,
  MoreHorizontal,
  ShieldHalf,
  Trash2,
  TriangleAlert,
  UserPen,
} from "lucide-react";
import * as React from "react";
import { useReportContext } from "@/components/report/context";
import { useDeleteReportAction } from "@/components/shell/delete-report";
import { ContextMenu, type MenuItem } from "@/components/ui/context-menu";
import { useToast } from "@/components/ui/toast";
import { HeadlineMetrics } from "@/components/report/headline-metrics";
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

/** The company name a report is shown under: the pack's, else the file name. */
export function reportName(report: ReturnType<typeof useReportContext>["report"]): string {
  return report.pack?.company_name ?? report.filename.replace(/\.pdf$/i, "");
}

export function ReportHeader() {
  const { report, current } = useReportContext();
  const pack = report.pack;
  const name = reportName(report);
  const status = STATUS[report.status] ?? { label: report.status, tone: "neutral" as Tone, Icon: Clock };
  const unitManual = pack?.warnings.some((w) => w.code === "unit_confirmed_manually") ?? false;
  const yearEnd = formatDate(current?.end_date);

  return (
    <header className="relative border-b border-line bg-surface" data-testid="report-header">
      <div aria-hidden className="hero-grid pointer-events-none absolute inset-0" />
      <div className="relative mx-auto max-w-[1600px] px-4 pt-7 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div className="min-w-0 space-y-2">
            <p className="eyebrow">{current ? `Annual report ${current.label}` : "Annual report"}</p>
            <h1
              className="truncate text-[1.875rem] font-semibold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[2.125rem]"
              data-testid="report-title"
            >
              {name}
            </h1>
            <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.8125rem] text-ink-2">
              {yearEnd ? (
                <span className="inline-flex items-center gap-1.5">
                  <CalendarDays aria-hidden className="size-3.5 text-ink-3" />
                  Year ended {yearEnd}
                </span>
              ) : null}
              {pack?.basis ? <span>{BASIS[pack.basis] ?? pack.basis} statements</span> : null}
              <span className="inline-flex items-center gap-1.5 font-mono text-[0.71875rem] text-ink-3">
                <FileText aria-hidden className="size-3.5" />
                {report.filename} · {report.page_count} pages
              </span>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={status.tone} data-testid="status-badge">
              <status.Icon aria-hidden />
              {status.label}
            </Badge>
            <Badge tone="neutral" data-testid="document-type-badge">
              {DOCUMENT_TYPES[report.document_type] ?? report.document_type}
            </Badge>
            {pack ? (
              <Badge tone="neutral" data-testid="unit-badge">
                <span className="num">{unitLabel(pack.currency, pack.unit_scale)}</span> {pack.currency}
              </Badge>
            ) : null}
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
            <ReportActions id={report.id} title={name} />
          </div>
        </div>
        <HeadlineMetrics />
        <div className="h-6" />
      </div>
    </header>
  );
}

/** The report's own actions, anchored to their button: copy its link or number, or delete it. */
function ReportActions({ id, title }: { id: number; title: string }) {
  const remove = useDeleteReportAction();
  const toast = useToast();
  const [at, setAt] = React.useState<{ x: number; y: number } | null>(null);
  const items: MenuItem[] = [
    {
      label: "Copy link",
      icon: <Link2 aria-hidden />,
      run: () => {
        void navigator.clipboard?.writeText(new URL(`/reports/${id}`, window.location.href).href);
        toast({ tone: "ok", title: "Link copied", body: title });
      },
    },
    { label: `Copy report number (${id})`, icon: <Copy aria-hidden />, run: () => void navigator.clipboard?.writeText(String(id)) },
    { label: "Delete report…", icon: <Trash2 aria-hidden />, destructive: true, run: () => void remove({ id, title }) },
  ];
  return (
    <>
      <Tooltip content="Report actions">
        <button
          type="button"
          aria-label="Report actions"
          aria-haspopup="menu"
          aria-expanded={at !== null}
          data-testid="report-actions"
          onClick={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            setAt({ x: r.left, y: r.bottom + 6 }); // opens under its button
          }}
          className="inline-flex size-7 items-center justify-center rounded-lg border border-line bg-surface text-ink-2 hover:bg-surface-sunk hover:text-ink"
        >
          <MoreHorizontal aria-hidden className="size-4" />
        </button>
      </Tooltip>
      <ContextMenu at={at} items={items} onClose={() => setAt(null)} />
    </>
  );
}

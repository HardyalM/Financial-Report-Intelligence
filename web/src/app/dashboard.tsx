"use client";

import {
  ArrowRight,
  Calculator,
  CircleAlert,
  Copy,
  ExternalLink,
  FileCheck2,
  Link2,
  Plus,
  Quote,
  Search,
  Sparkles,
} from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Kbd } from "@/components/pdf/toolbar";
import { shortcutLabel } from "@/components/pdf/use-viewer-input";
import { SiteFooter } from "@/components/report/footer";
import { usePalette } from "@/components/shell/command-palette";
import { reportTitle, statusMeta, whenAdded } from "@/components/shell/report-meta";
import { useUpload } from "@/components/shell/upload";
import { Badge } from "@/components/ui/badge";
import { ContextMenu, type MenuItem } from "@/components/ui/context-menu";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { unitLabel } from "@/lib/format";
import { DOCUMENT_TYPES } from "@/lib/items";
import { spring, useSafeMotion } from "@/lib/motion";
import { type ReportSummary, usePrefetchReport, useReports } from "@/lib/queries";
import { OpenReport } from "./open-report";
import { UploadDropzone } from "./upload-dropzone";

type Filter = "all" | "ready" | "waiting" | "moving";

const WAITING = new Set(["needs_unit_confirmation", "needs_document_type", "failed"]);
const MOVING = new Set(["queued", "processing"]);
const needsYou = (r: ReportSummary) => WAITING.has(r.status) || r.open_review_items > 0;

/** The dashboard: every report, what each is waiting for, and the way to add one. */
export function Dashboard() {
  const reports = useReports();
  if (reports.isPending) return <DashboardSkeleton />;
  if (reports.isError || reports.data.length === 0) {
    return <Onboarding unavailable={reports.isError} />;
  }
  return <ReportList reports={reports.data} />;
}

// ---------------------------------------------------------------------------- the dashboard

function ReportList({ reports }: { reports: ReportSummary[] }) {
  const [filter, setFilter] = React.useState<Filter>("all");
  const [query, setQuery] = React.useState("");
  const search = React.useRef<HTMLInputElement>(null);
  const palette = usePalette();

  // "/" puts the cursor in the filter, as in most desktop apps.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(t.tagName) && !t.isContentEditable) {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const counts = {
    all: reports.length,
    ready: reports.filter((r) => r.status === "ready" && !needsYou(r)).length,
    waiting: reports.filter(needsYou).length,
    moving: reports.filter((r) => MOVING.has(r.status)).length,
  };
  const q = query.trim().toLowerCase();
  const shown = reports.filter((r) => {
    if (filter === "ready" && !(r.status === "ready" && !needsYou(r))) return false;
    if (filter === "waiting" && !needsYou(r)) return false;
    if (filter === "moving" && !MOVING.has(r.status)) return false;
    return !q || `${reportTitle(r)} ${r.filename} ${r.id}`.toLowerCase().includes(q);
  });

  return (
    <div className="flex flex-1 flex-col">
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-6 lg:px-8" data-testid="dashboard">
        <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
          <div className="space-y-1.5">
            <p className="eyebrow">Workspace</p>
            <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.03em] text-ink">Reports</h1>
            <p className="text-[0.84375rem] text-ink-3">
              {counts.all} report{counts.all === 1 ? "" : "s"} read
              {counts.waiting ? ` · ${counts.waiting} waiting for you` : ""}
              {counts.moving ? ` · ${counts.moving} in progress` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => palette.open()}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-[0.8125rem] text-ink-2 shadow-[var(--shadow-card)] transition-colors hover:text-ink"
          >
            <Sparkles aria-hidden className="size-4 text-accent" />
            Everything else
            <Kbd>{shortcutLabel("mod+k")}</Kbd>
          </button>
        </div>

        <div className="grid grid-cols-1 gap-8 2xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-5">
            <div role="tablist" aria-label="Filter reports" className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line shadow-[var(--shadow-card)] sm:grid-cols-4">
              {(
                [
                  ["all", "All reports"],
                  ["ready", "Ready"],
                  ["waiting", "Waiting for you"],
                  ["moving", "In progress"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={filter === id}
                  onClick={() => setFilter(id)}
                  data-testid={`filter-${id}`}
                  className={cn(
                    "relative flex flex-col items-start gap-1.5 bg-surface px-4 py-3.5 text-left transition-colors hover:bg-surface-sunk/60",
                    filter === id && "bg-surface-sunk/80",
                  )}
                >
                  <span className="eyebrow">{label}</span>
                  <span className={cn("display-figure text-[1.5rem]", id === "waiting" && counts.waiting ? "text-review" : "text-ink")}>{counts[id]}</span>
                  {filter === id ? (
                    <motion.span layoutId="filter-underline" transition={spring.snappy} className="absolute inset-x-0 bottom-0 h-[2px] bg-ink" />
                  ) : null}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 shadow-[var(--shadow-card)] focus-within:border-accent/50">
              <Search aria-hidden className="size-4 text-ink-3" />
              <input
                ref={search}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") (setQuery(""), e.currentTarget.blur());
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    document.querySelector<HTMLElement>("[data-report-row]")?.focus();
                  }
                }}
                placeholder="Filter by company, file or number"
                aria-label="Filter reports"
                data-testid="dashboard-filter"
                className="h-10 flex-1 bg-transparent text-[0.84375rem] text-ink outline-none placeholder:text-ink-3"
              />
              <Kbd>/</Kbd>
            </div>

            {shown.length ? (
              <ReportTable reports={shown} />
            ) : (
              <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-line-strong bg-surface/60 px-6 py-14 text-center" data-testid="dashboard-no-match">
                <Search aria-hidden className="size-5 text-ink-3" />
                <p className="text-[0.875rem] font-medium text-ink">No reports match</p>
                <p className="text-[0.78125rem] text-ink-3">Clear the filter to see all {counts.all}.</p>
                <button
                  type="button"
                  onClick={() => (setQuery(""), setFilter("all"))}
                  className="mt-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-[0.78125rem] font-medium text-ink hover:bg-surface-sunk"
                >
                  Show all reports
                </button>
              </div>
            )}
          </div>

          <aside className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] 2xl:block 2xl:space-y-4" aria-label="Add a report">
            <div className="space-y-4 rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
              <div className="space-y-1">
                <p className="eyebrow">Add</p>
                <h2 className="text-[1rem] font-semibold tracking-[-0.015em] text-ink">Analyse a report</h2>
              </div>
              <UploadDropzone compact />
              <div className="space-y-2 border-t border-line pt-4">
                <p className="text-[0.78125rem] text-ink-3">Or open a report already read:</p>
                <OpenReport />
              </div>
            </div>
            <p className="px-1 text-[0.75rem] leading-relaxed text-ink-3">
              Drop a PDF anywhere in the app to add it. Figures and ratios are computed locally; commentary uses the
              model provider you configured, if any.
            </p>
          </aside>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

function ReportTable({ reports }: { reports: ReportSummary[] }) {
  const safe = useSafeMotion(); // reduced motion: these fade instead of moving
  // Arrow keys move between rows; Enter opens (the row is a link).
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const rows = [...document.querySelectorAll<HTMLElement>("[data-report-row]")];
    const i = rows.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    e.preventDefault();
    if (e.key === "ArrowUp" && i === 0) return document.querySelector<HTMLElement>("[data-testid=dashboard-filter]")?.focus();
    rows[Math.min(rows.length - 1, Math.max(0, i + (e.key === "ArrowDown" ? 1 : -1)))]?.focus();
  };
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" onKeyDown={onKeyDown}>
      <div className="hidden grid-cols-[minmax(0,1fr)_64px_92px_minmax(150px,190px)_56px_96px] gap-4 border-b border-line bg-surface-sunk/60 px-4 py-2.5 md:grid">
        {["Report", "Period", "Type", "Status", "Pages", "Added"].map((h, i) => (
          <span key={h} className={cn("eyebrow", (i === 1 || i === 4) && "text-right")}>
            {h}
          </span>
        ))}
      </div>
      <ul data-testid="report-list">
        {reports.map((r, i) => (
          <motion.li
            key={r.id}
            layout="position"
            initial={safe({ opacity: 0, y: 4 })}
            animate={safe({ opacity: 1, y: 0 })}
            transition={spring.snappy}
            className="border-b border-line last:border-b-0"
          >
            <ReportRowLink report={r} />
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

function ReportRowLink({ report }: { report: ReportSummary }) {
  const router = useRouter();
  const prefetch = usePrefetchReport();
  const toast = useToast();
  const [menu, setMenu] = React.useState<{ x: number; y: number } | null>(null);
  const status = statusMeta(report.status);
  const title = reportTitle(report);
  const href = `/reports/${report.id}`;
  const waiting = report.open_review_items;
  const items: MenuItem[] = [
    { label: "Open", hint: "↵", icon: <ExternalLink aria-hidden />, run: () => router.push(href) },
    { label: "Open in a new tab", icon: <ExternalLink aria-hidden />, run: () => window.open(href, "_blank", "noopener") },
    {
      label: "Copy link",
      icon: <Link2 aria-hidden />,
      run: () => {
        void navigator.clipboard?.writeText(new URL(href, window.location.href).href);
        toast({ tone: "ok", title: "Link copied", body: title });
      },
    },
    { label: `Copy report number (${report.id})`, icon: <Copy aria-hidden />, run: () => void navigator.clipboard?.writeText(String(report.id)) },
  ];
  return (
    <>
      <a
        href={href}
        data-report-row
        data-testid="report-row"
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
          e.preventDefault();
          router.push(href);
        }}
        onPointerEnter={() => prefetch(report.id)}
        onFocus={() => prefetch(report.id)}
        onContextMenu={(e) => {
          e.preventDefault();
          setMenu({ x: e.clientX, y: e.clientY });
        }}
        className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3 outline-none transition-colors duration-100 hover:bg-surface-sunk/70 active:bg-surface-sunk active:duration-0 focus-visible:bg-accent-soft/60 md:grid-cols-[minmax(0,1fr)_64px_92px_minmax(150px,190px)_56px_96px]"
      >
        <span className="flex min-w-0 items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-line bg-surface-sunk text-[0.8125rem] font-semibold uppercase text-ink-2">
            {title.charAt(0)}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[0.875rem] font-medium tracking-[-0.01em] text-ink">{title}</span>
            <span className="block truncate font-mono text-[0.71875rem] text-ink-3">
              {report.filename}
              {report.currency ? ` · ${unitLabel(report.currency, report.unit_scale)} ${report.currency}` : ""}
            </span>
          </span>
        </span>
        <span className="num hidden text-right text-[0.8125rem] text-ink-2 md:block">{report.period_label ?? "—"}</span>
        <span className="hidden md:block">
          <Badge tone="neutral">{DOCUMENT_TYPES[report.document_type] ?? report.document_type}</Badge>
        </span>
        <span className="flex flex-wrap items-center justify-end gap-1.5 md:justify-start">
          <Badge tone={status.tone} data-testid="report-row-status">
            <status.Icon aria-hidden className={cn(status.spinning && "animate-spin motion-reduce:animate-none")} />
            {status.label}
          </Badge>
          {waiting ? (
            <Badge tone="review">
              <CircleAlert aria-hidden />
              {waiting} to review
            </Badge>
          ) : null}
        </span>
        <span className="num hidden text-right text-[0.8125rem] text-ink-3 md:block">{report.page_count || "—"}</span>
        <span className="hidden items-center justify-between text-[0.78125rem] text-ink-3 md:flex">
          {whenAdded(report.created_at)}
          <ArrowRight aria-hidden className="size-4 -translate-x-1 opacity-0 transition-[opacity,transform] duration-150 group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:opacity-100" />
        </span>
      </a>
      <ContextMenu at={menu} items={items} onClose={() => setMenu(null)} />
    </>
  );
}

// ---------------------------------------------------------------------------- empty / first run

const PROMISES = [
  { Icon: FileCheck2, title: "Figures from the statements", body: "Read from the income statement and balance sheet, checked by arithmetic, each with its page." },
  { Icon: Calculator, title: "Ratios computed in code", body: "Locked definitions, year-end balances, every input shown. Never written by a model." },
  { Icon: Quote, title: "Commentary that cites", body: "Every sentence carries a quote that code found in the report, one click from its page." },
];

function Onboarding({ unavailable }: { unavailable: boolean }) {
  const upload = useUpload();
  const palette = usePalette();
  return (
    <div className="flex flex-1 flex-col">
      <main className="relative flex-1" data-testid="onboarding">
        <div aria-hidden className="hero-grid pointer-events-none absolute inset-x-0 top-0 h-[520px]" />
        <div className="relative mx-auto grid max-w-[1200px] grid-cols-1 items-center gap-12 px-4 pb-16 pt-12 sm:px-6 lg:grid-cols-[minmax(0,1fr)_460px] lg:px-8 lg:pt-16">
          <div className="space-y-9">
            <div className="space-y-5">
              <p className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[0.75rem] font-medium text-ink-2 shadow-[var(--shadow-card)]">
                <span aria-hidden className="size-1.5 rounded-full bg-ok" />
                UK annual reports · digitally born PDFs
              </p>
              <h1 className="max-w-xl text-[2.5rem] font-semibold leading-[1.05] tracking-[-0.035em] text-ink sm:text-[3.125rem]">
                Financial Report Intelligence
              </h1>
              <p className="max-w-xl text-[1rem] leading-relaxed text-ink-2">
                Figures read from the statements and checked by arithmetic, ratios computed in code, and commentary that
                cites the page it comes from. When a figure can’t be verified, it stays empty and says why.
              </p>
              <div className="flex flex-wrap items-center gap-2.5">
                <button
                  type="button"
                  onClick={upload.pick}
                  className="inline-flex h-10 items-center gap-2 rounded-xl bg-ink px-4 text-[0.875rem] font-medium text-ink-inverse shadow-[var(--shadow-raised)] transition-[opacity,transform] hover:opacity-90 active:scale-[0.98]"
                >
                  <Plus aria-hidden className="size-4" />
                  Analyse your first report
                </button>
                <button
                  type="button"
                  onClick={() => palette.open()}
                  className="inline-flex h-10 items-center gap-2 rounded-xl border border-line bg-surface px-3.5 text-[0.84375rem] text-ink-2 hover:text-ink"
                >
                  Command menu <Kbd>{shortcutLabel("mod+k")}</Kbd>
                </button>
              </div>
            </div>
            <ul className="grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3">
              {PROMISES.map(({ Icon, title, body }) => (
                <li key={title} className="space-y-2 bg-surface p-5">
                  <span className="inline-flex size-8 items-center justify-center rounded-lg bg-accent-soft">
                    <Icon aria-hidden className="size-4 text-accent" />
                  </span>
                  <p className="text-[0.84375rem] font-semibold tracking-[-0.01em] text-ink">{title}</p>
                  <p className="text-[0.78125rem] leading-relaxed text-ink-3">{body}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="space-y-4">
            <EmptyIllustration />
            <div className="space-y-5 rounded-3xl border border-line bg-surface p-5 shadow-[var(--shadow-pop)] sm:p-6">
              {unavailable ? (
                <p role="status" className="flex items-start gap-2 rounded-xl border border-review-line bg-review-soft px-3 py-2.5 text-[0.78125rem] leading-relaxed text-ink-2" data-testid="reports-unavailable">
                  <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-review" />
                  Your reports couldn’t be listed just now. You can still add one, or open one by its number.
                </p>
              ) : null}
              <UploadDropzone />
              <div className="space-y-2 border-t border-line pt-5">
                <p className="text-[0.78125rem] text-ink-3">Or open a report already read:</p>
                <OpenReport />
              </div>
            </div>
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

/** A stack of report pages, the top one with a highlighted figure: what this product does. */
function EmptyIllustration() {
  return (
    <svg viewBox="0 0 460 150" className="w-full" aria-hidden>
      <defs>
        <linearGradient id="ill-fade" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="var(--surface)" />
          <stop offset="1" stopColor="var(--surface-sunk)" />
        </linearGradient>
      </defs>
      {[0, 1, 2].map((i) => (
        <g key={i} transform={`translate(${150 + i * 26} ${30 - i * 10}) rotate(${(i - 1) * 4} 80 60)`}>
          <rect width="160" height="118" rx="10" fill="url(#ill-fade)" stroke="var(--line-strong)" />
          {i === 2 ? (
            <>
              <rect x="16" y="16" width="70" height="7" rx="3.5" fill="var(--ink-3)" opacity="0.5" />
              {[0, 1, 2, 3, 4].map((r) => (
                <g key={r}>
                  <rect x="16" y={36 + r * 14} width="78" height="5" rx="2.5" fill="var(--line-strong)" />
                  <rect x="110" y={36 + r * 14} width="34" height="5" rx="2.5" fill="var(--line-strong)" />
                </g>
              ))}
              <rect x="104" y="44.5" width="46" height="16" rx="4" fill="var(--highlight)" stroke="oklch(0.75 0.16 85)" />
              <rect x="110" y="50" width="34" height="5" rx="2.5" fill="var(--ink-2)" />
            </>
          ) : null}
        </g>
      ))}
      <g transform="translate(96 74)">
        <circle r="22" fill="var(--surface)" stroke="var(--line-strong)" />
        <path d="M-8 1 l5 5 l11 -12" fill="none" stroke="var(--ok)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <g transform="translate(370 112)">
        <rect x="-44" y="-15" width="88" height="30" rx="15" fill="var(--surface)" stroke="var(--line-strong)" />
        <text x="0" y="5" textAnchor="middle" fontSize="12" fontWeight="600" fill="var(--ink-2)" fontFamily="var(--font-sans)">
          p. 141
        </text>
      </g>
    </svg>
  );
}

// ---------------------------------------------------------------------------- loading

/** The dashboard's own shape, so nothing moves when the list arrives. */
function DashboardSkeleton() {
  return (
    <div className="flex flex-1 flex-col" aria-busy="true" aria-live="polite">
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-6 lg:px-8" data-testid="dashboard-skeleton">
        <div className="mb-7 space-y-2.5">
          <div className="h-[13px] w-20 animate-pulse rounded bg-ink/[0.06]" />
          <div className="h-[35px] w-40 animate-pulse rounded-lg bg-ink/[0.07]" />
          <div className="h-[20px] w-56 animate-pulse rounded bg-ink/[0.05]" />
        </div>
        <div className="grid grid-cols-1 gap-8 2xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-5">
            <div className="h-[82px] animate-pulse rounded-2xl bg-ink/[0.05]" />
            <div className="h-[42px] animate-pulse rounded-xl bg-ink/[0.05]" />
            <div className="overflow-hidden rounded-2xl border border-line bg-surface">
              {Array.from({ length: 5 }, (_, i) => (
                <div key={i} className="flex h-[63px] items-center gap-3 border-b border-line px-4 last:border-b-0">
                  <div className="size-9 animate-pulse rounded-xl bg-ink/[0.06]" />
                  <div className="space-y-1.5">
                    <div className="h-3.5 w-48 animate-pulse rounded bg-ink/[0.07]" />
                    <div className="h-3 w-32 animate-pulse rounded bg-ink/[0.05]" />
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="h-[380px] animate-pulse rounded-2xl bg-ink/[0.04]" />
        </div>
        <span className="sr-only">Loading your reports</span>
      </main>
    </div>
  );
}



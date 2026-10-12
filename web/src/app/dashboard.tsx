"use client";

import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Calculator,
  CircleAlert,
  CircleCheck,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  FileCheck2,
  FlaskConical,
  Link2,
  Loader,
  Lock,
  Plus,
  Quote,
  Search,
  Sparkles,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Kbd } from "@/components/pdf/toolbar";
import { shortcutLabel } from "@/components/pdf/use-viewer-input";
import { SiteFooter } from "@/components/report/footer";
import { usePalette } from "@/components/shell/command-palette";
import { statusMeta, whenAdded } from "@/components/shell/report-meta";
import { useUpload } from "@/components/shell/upload";
import { Badge } from "@/components/ui/badge";
import { ContextMenu, type MenuItem } from "@/components/ui/context-menu";
import { useToast } from "@/components/ui/toast";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { formatRatio, formatRatioChange, shownDirection, unitLabel } from "@/lib/format";
import { DOCUMENT_TYPES } from "@/lib/items";
import { spring, useSafeMotion } from "@/lib/motion";
import { type ReportCard, useDashboard, usePrefetchReport, useSamples, useShowSamples } from "@/lib/queries";
import { OpenReport } from "./open-report";
import { UploadDropzone } from "./upload-dropzone";

/**
 * The dashboard leads with what the product produces: for the latest report, its ratios as the
 * engine computed them and how every figure was settled (read and anchored to the page, derived in
 * code, set by a person, or left empty with the reason). Then what waits for a person, what is
 * being read now, and the library. Every number here is the server's; none is computed on screen.
 */
export function Dashboard() {
  const q = useDashboard();
  const [showSamples] = useShowSamples();
  if (q.isPending) return <DashboardView cards={null} hasSamples={false} />;
  if (q.isError) return <Onboarding unavailable />;
  if (q.data.reports.length === 0) return <Onboarding unavailable={false} />;
  const cards = showSamples ? q.data.reports : q.data.reports.filter((c) => !c.is_sample);
  return <DashboardView cards={cards} hasSamples={q.data.has_samples} />;
}

// ---------------------------------------------------------------------------- layout

/** One layout for data and for loading (`cards` null): the skeleton is the page, so nothing moves. */
function DashboardView({ cards, hasSamples }: { cards: ReportCard[] | null; hasSamples: boolean }) {
  const palette = usePalette();
  const upload = useUpload();
  const loading = cards === null;
  const spotlight = cards ? (cards.find((c) => c.status === "ready" && c.figures) ?? cards.find((c) => c.figures) ?? null) : null;
  const waiting = cards?.filter((c) => c.waiting_for) ?? [];
  const reading = cards?.filter((c) => c.status === "queued" || c.status === "processing") ?? [];

  return (
    <div className="flex flex-1 flex-col">
      <main
        className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-6 lg:px-8"
        data-testid={loading ? "dashboard-skeleton" : "dashboard"}
        aria-busy={loading || undefined}
      >
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div className="space-y-1.5">
            <p className="eyebrow">Workspace</p>
            <h1 className="text-[1.75rem] font-semibold leading-tight text-ink">Reports</h1>
            <p className="max-w-xl text-[0.84375rem] leading-relaxed text-ink-3">
              Figures read from the statements and anchored to their page, ratios computed in code, commentary that cites
              its source. What can’t be verified stays empty, with the reason.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {hasSamples ? <SampleControls /> : <AddSamples />}
            <button
              type="button"
              onClick={() => palette.open()}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-[0.8125rem] text-ink-2 shadow-[var(--shadow-card)] transition-colors hover:text-ink"
            >
              <Sparkles aria-hidden className="size-4 text-accent" />
              Search
              <Kbd>{shortcutLabel("mod+k")}</Kbd>
            </button>
            <button
              type="button"
              onClick={upload.pick}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-3.5 text-[0.8125rem] font-medium text-ink-inverse shadow-[var(--shadow-card)] hover:opacity-90"
            >
              <Plus aria-hidden className="size-4" />
              Analyse a report
            </button>
          </div>
        </header>

        <section aria-labelledby="latest-heading" className="mb-10">
          <h2 id="latest-heading" className="eyebrow mb-3">
            Latest result
          </h2>
          {loading ? <Spotlight card={null} /> : spotlight ? <Spotlight card={spotlight} /> : <NoResultYet />}
        </section>

        <div className="mb-10 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <section aria-labelledby="waiting-heading">
            <h2 id="waiting-heading" className="eyebrow mb-3">
              Waiting for you {cards ? <span className="num text-ink-2">· {waiting.length}</span> : null}
            </h2>
            <WaitingQueue cards={loading ? null : waiting} />
          </section>
          <section aria-labelledby="reading-heading">
            <h2 id="reading-heading" className="eyebrow mb-3">
              {reading.length ? "Being read now" : "Add a report"}
              {reading.length ? <span className="num text-ink-2"> · {reading.length}</span> : null}
            </h2>
            {loading ? <QueueSkeleton rows={1} /> : reading.length ? <ReadingNow cards={reading} /> : <AddReport />}
          </section>
        </div>

        <section aria-labelledby="library-heading">
          <div className="mb-3 flex items-end justify-between gap-4">
            <h2 id="library-heading" className="eyebrow">
              Library {cards ? <span className="num text-ink-2">· {cards.length}</span> : null}
            </h2>
            <Legend />
          </div>
          <Library cards={cards} />
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

// ---------------------------------------------------------------------------- latest result

const RATIO_SLOTS = 4;

function Spotlight({ card }: { card: ReportCard | null }) {
  const prefetch = usePrefetchReport();
  const status = card ? statusMeta(card.status) : null;
  const ratios = card?.ratios.slice(0, RATIO_SLOTS) ?? [];
  return (
    <article
      data-testid="spotlight"
      className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-raised)]"
      onPointerEnter={() => card && prefetch(card.id)}
    >
      <div className="flex min-h-[5.6875rem] flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
        <div className="min-w-0 space-y-1.5">
          {card ? (
            <>
              <p className="flex min-h-[1.125rem] flex-wrap items-center gap-2 text-[0.75rem] text-ink-3">
                <span className="num">
                  {card.period_label ? `FY ${card.period_label}` : "Period not read"}
                  {card.prior_label ? ` vs ${card.prior_label}` : ""}
                </span>
                <span aria-hidden>·</span>
                <span>{DOCUMENT_TYPES[card.document_type] ?? card.document_type}</span>
                {card.currency ? (
                  <>
                    <span aria-hidden>·</span>
                    <span className="num">
                      {unitLabel(card.currency, card.unit_scale)} {card.currency}
                    </span>
                  </>
                ) : null}
                {card.is_sample ? <SampleTag /> : null}
              </p>
              <h3 className="truncate text-[1.5rem] font-semibold leading-tight text-ink" data-testid="spotlight-title">
                {card.title}
              </h3>
            </>
          ) : (
            <>
              <Bone className="h-[1.125rem] w-48" />
              <Bone className="h-[1.8125rem] w-72 max-w-full" />
            </>
          )}
        </div>
        {card && status ? (
          <div className="flex items-center gap-2">
            <Badge tone={status.tone}>
              <status.Icon aria-hidden />
              {status.label}
            </Badge>
            <Link
              href={`/reports/${card.id}`}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-3.5 text-[0.8125rem] font-medium text-ink-inverse shadow-[var(--shadow-card)] hover:opacity-90 active:scale-[0.97] active:duration-0"
              data-testid="spotlight-open"
            >
              Open report
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
        ) : (
          <Bone className="h-9 w-36 rounded-lg" />
        )}
      </div>

      <div className="grid grid-cols-2 gap-px bg-line md:grid-cols-4" data-testid="spotlight-ratios">
        {Array.from({ length: RATIO_SLOTS }, (_, i) => (
          <div key={i} className="bg-surface px-5 py-4 sm:px-6">
            {card ? ratios[i] ? <RatioTile r={ratios[i]!} prior={card.prior_label} /> : <EmptyTile /> : <TileBone />}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-x-8 gap-y-4 px-5 py-4 sm:px-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-2">
          <p className="eyebrow">How the figures were settled</p>
          {card?.figures ? <SettlementBar counts={card.figures} /> : <Bone className="h-[2.75rem] w-full" />}
        </div>
        <div className="space-y-2">
          <p className="eyebrow">Commentary</p>
          {card ? <CommentaryLine card={card} /> : <Bone className="h-[2.75rem] w-full" />}
        </div>
      </div>
    </article>
  );
}

type Ratio = ReportCard["ratios"][number];

function RatioTile({ r, prior }: { r: Ratio; prior: string | null }) {
  const change = r.value != null && r.change != null && r.change_kind ? formatRatioChange(r.change_kind, r.change) : null;
  const d = change ? shownDirection(change) : 0;
  const Arrow = d > 0 ? ArrowUpRight : d < 0 ? ArrowDownRight : ArrowRight;
  const negative = r.flags.includes("negative_denominator");
  return (
    <div className="space-y-2" data-testid="spotlight-ratio" data-ratio={r.name}>
      <p className="eyebrow truncate">{r.label}</p>
      <p className="flex min-h-[2.125rem] items-baseline gap-2">
        {r.value != null ? (
          <span className="display-figure text-[1.875rem] text-ink" data-testid="spotlight-ratio-value">
            {formatRatio(r.value, r.unit)}
          </span>
        ) : (
          <span className="display-figure text-[1.875rem] text-ink-3" aria-label="not computed">
            —
          </span>
        )}
      </p>
      <p className="num flex min-h-[1.0625rem] flex-wrap items-center gap-x-2 text-[0.71875rem] text-ink-3">
        {r.value == null ? (
          <span>Not computed: an input is empty</span>
        ) : (
          <>
            {change ? (
              <span className="inline-flex items-center gap-0.5 font-medium text-ink-2">
                <Arrow aria-hidden className="size-3.5" />
                {change}
              </span>
            ) : null}
            {prior && change ? <span>vs {prior}</span> : null}
            {negative ? <span className="text-amber">Not meaningful</span> : null}
          </>
        )}
      </p>
    </div>
  );
}

function EmptyTile() {
  return (
    <div className="space-y-2" aria-hidden>
      <p className="min-h-[0.9375rem]" />
      <p className="min-h-[2.125rem]" />
      <p className="min-h-[1.0625rem]" />
    </div>
  );
}

function TileBone() {
  return (
    <div className="space-y-2">
      <Bone className="h-[0.9375rem] w-24" />
      <Bone className="h-[2.125rem] w-28" />
      <Bone className="h-[1.0625rem] w-20" />
    </div>
  );
}

const SEGMENTS = [
  { key: "read", label: "Read and anchored", className: "bg-ok" },
  { key: "derived", label: "Derived in code", className: "bg-derived" },
  { key: "manual", label: "Set by a person", className: "bg-amber" },
  { key: "empty", label: "Left empty, with the reason", className: "bg-ink/15" },
] as const;

/** How every current-period figure was settled, as one bar and its counts. */
function SettlementBar({ counts }: { counts: NonNullable<ReportCard["figures"]> }) {
  const total = counts.read + counts.derived + counts.manual + counts.empty;
  const safe = useSafeMotion();
  return (
    <div className="space-y-2" data-testid="settlement">
      <div
        role="img"
        aria-label={SEGMENTS.map((s) => `${counts[s.key]} ${s.label.toLowerCase()}`).join(", ")}
        className="flex h-2 overflow-hidden rounded-full bg-ink/[0.06]"
      >
        {SEGMENTS.map((s) =>
          counts[s.key] ? (
            <motion.span
              key={s.key}
              className={cn("h-full origin-left", s.className)}
              style={{ width: `${(counts[s.key] / total) * 100}%` }}
              initial={safe({ scaleX: 0, opacity: 0 })}
              animate={safe({ scaleX: 1, opacity: 1 }, 1)}
              transition={spring.page}
            />
          ) : null,
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[0.75rem] text-ink-2">
        {SEGMENTS.map((s) => (
          <li key={s.key} className="inline-flex items-center gap-1.5">
            <span aria-hidden className={cn("size-2 rounded-full", s.className)} />
            <span className={cn("num font-semibold", counts[s.key] ? "text-ink" : "text-ink-3")} data-testid={`settled-${s.key}`}>
              {counts[s.key]}
            </span>
            {s.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CommentaryLine({ card }: { card: ReportCard }) {
  const c = card.commentary;
  if (!c) {
    return <p className="min-h-[2.75rem] text-[0.8125rem] leading-relaxed text-ink-3">Not written yet: it follows the figures.</p>;
  }
  return (
    <p className="flex min-h-[2.75rem] flex-wrap items-center gap-x-2 gap-y-1 text-[0.8125rem] leading-relaxed text-ink-2" data-testid="spotlight-commentary">
      <Quote aria-hidden className="size-3.5 text-ink-3" />
      <span>
        <span className="num font-semibold text-ink">{c.citations}</span> cited passage{c.citations === 1 ? "" : "s"} ·{" "}
        <span className="num">{c.topics_ok}</span> of <span className="num">{c.topics}</span> topics evidenced
      </span>
      {c.mode === "extractive" ? <Badge tone="neutral">Extractive: no generated text</Badge> : null}
      {c.stale ? <Badge tone="amber">Figures changed since</Badge> : null}
    </p>
  );
}

function NoResultYet() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-line-strong bg-surface/60 px-6 py-12 text-center">
      <Loader aria-hidden className="size-5 text-ink-3" />
      <p className="text-[0.875rem] font-medium text-ink">No figures read yet</p>
      <p className="max-w-sm text-[0.78125rem] text-ink-3">
        The first report’s figures and ratios appear here as soon as its statements have been read and checked.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------- waiting / reading

const WAITING: Record<string, { action: (c: ReportCard) => string; why: string; Icon: typeof Lock }> = {
  unit: { action: () => "Confirm the unit", why: "The statements don’t say whether figures are in thousands or millions.", Icon: Lock },
  document_type: { action: () => "Set the document type", why: "Ratios are withheld until it is known which ones apply.", Icon: TriangleAlert },
  review: {
    action: (c) => `Review ${c.open_review_items} figure${c.open_review_items === 1 ? "" : "s"}`,
    why: "Engines disagreed or a check failed: a person decides.",
    Icon: CircleAlert,
  },
  failed: { action: () => "See what stopped", why: "Processing stopped after its retries.", Icon: TriangleAlert },
};

function WaitingQueue({ cards }: { cards: ReportCard[] | null }) {
  if (cards === null) return <QueueSkeleton rows={2} />;
  if (!cards.length) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface px-5 py-4 shadow-[var(--shadow-card)]" data-testid="waiting-empty">
        <CircleCheck aria-hidden className="size-5 shrink-0 text-ok" />
        <div>
          <p className="text-[0.84375rem] font-medium text-ink">Nothing is waiting for you</p>
          <p className="text-[0.75rem] text-ink-3">Reports that need a decision (a unit, a document type, a disputed figure) appear here.</p>
        </div>
      </div>
    );
  }
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" data-testid="waiting">
      {cards.map((c) => {
        const w = WAITING[c.waiting_for!]!;
        return (
          <li key={c.id}>
            <RowLink card={c} className="flex items-center gap-3 px-4 py-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-review-soft text-review">
                <w.Icon aria-hidden className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate text-[0.84375rem] font-medium text-ink">{c.title}</span>
                  {c.is_sample ? <SampleTag /> : null}
                </span>
                <span className="block truncate text-[0.75rem] text-ink-3">{w.why}</span>
              </span>
              <span className="hidden shrink-0 items-center gap-1 text-[0.78125rem] font-medium text-accent sm:inline-flex" data-testid="waiting-action">
                {w.action(c)}
                <ArrowRight aria-hidden className="size-3.5" />
              </span>
            </RowLink>
          </li>
        );
      })}
    </ul>
  );
}

const STAGES = [
  ["ingest", "Intake"],
  ["text_layer", "Reading pages"],
  ["extract", "Extracting figures"],
  ["ratios", "Calculating ratios"],
  ["index", "Indexing narrative"],
  ["commentary", "Writing commentary"],
] as const;

function ReadingNow({ cards }: { cards: ReportCard[] }) {
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" data-testid="reading">
      {cards.map((c) => {
        const byStage = new Map(c.jobs.map((j) => [j.stage, j.status]));
        const running = STAGES.find(([s]) => byStage.get(s) === "running") ?? STAGES.find(([s]) => byStage.get(s) !== "done");
        return (
          <li key={c.id}>
            <RowLink card={c} className="block px-4 py-3">
              <span className="flex items-center justify-between gap-3">
                <span className="truncate text-[0.84375rem] font-medium text-ink">{c.title}</span>
                <span className="inline-flex shrink-0 items-center gap-1.5 text-[0.75rem] text-ink-3" aria-live="polite">
                  <Loader aria-hidden className="size-3.5 animate-spin text-accent motion-reduce:animate-none" />
                  {running?.[1] ?? "Queued"}
                </span>
              </span>
              <span className="mt-2 grid grid-cols-6 gap-1" aria-label={`Stages: ${c.jobs.map((j) => `${j.stage} ${j.status}`).join(", ")}`}>
                {STAGES.map(([s]) => (
                  <span
                    key={s}
                    className={cn(
                      "h-1 rounded-full",
                      byStage.get(s) === "done" ? "bg-ok" : byStage.get(s) === "running" ? "animate-pulse bg-accent motion-reduce:animate-none" : "bg-ink/10",
                    )}
                  />
                ))}
              </span>
            </RowLink>
          </li>
        );
      })}
    </ul>
  );
}

function AddReport() {
  return (
    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
      <UploadDropzone compact />
      <div className="space-y-2 border-t border-line pt-4">
        <p className="text-[0.78125rem] text-ink-3">Or open a report already read:</p>
        <OpenReport />
      </div>
    </div>
  );
}

function QueueSkeleton({ rows }: { rows: number }) {
  return (
    <div className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex h-[3.875rem] items-center gap-3 px-4">
          <Bone className="size-8 rounded-lg" />
          <div className="flex-1 space-y-1.5">
            <Bone className="h-3.5 w-40" />
            <Bone className="h-3 w-64 max-w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------- library

function Legend() {
  return (
    <ul className="hidden flex-wrap gap-x-3 text-[0.6875rem] text-ink-3 md:flex" aria-hidden>
      {SEGMENTS.map((s) => (
        <li key={s.key} className="inline-flex items-center gap-1">
          <span className={cn("size-1.5 rounded-full", s.className)} />
          {s.label.split(",")[0]}
        </li>
      ))}
    </ul>
  );
}

// Columns appear as there is room: name and status always; the headline ratio from md; the
// settlement bar and the date from xl. The name column never shrinks below 12rem.
const LIBRARY_COLUMNS =
  "md:grid-cols-[minmax(12rem,1fr)_6.5rem_minmax(8rem,11rem)] xl:grid-cols-[minmax(14rem,1fr)_minmax(8rem,11rem)_6.5rem_minmax(9rem,11rem)_5.5rem]";

function Library({ cards }: { cards: ReportCard[] | null }) {
  const [query, setQuery] = React.useState("");
  const search = React.useRef<HTMLInputElement>(null);
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
  const q = query.trim().toLowerCase();
  const shown = cards?.filter((c) => !q || `${c.title} ${c.filename} ${c.id}`.toLowerCase().includes(q)) ?? null;

  // Arrow keys move between rows; ↑ from the first row returns to the filter; Enter opens.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const rows = [...document.querySelectorAll<HTMLElement>("[data-report-row]")];
    const i = rows.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    e.preventDefault();
    if (e.key === "ArrowUp" && i === 0) return search.current?.focus();
    rows[Math.min(rows.length - 1, Math.max(0, i + (e.key === "ArrowDown" ? 1 : -1)))]?.focus();
  };

  return (
    <div className="space-y-3">
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
          disabled={!cards}
          className="h-10 flex-1 bg-transparent text-[0.84375rem] text-ink outline-none placeholder:text-ink-3"
        />
        <Kbd>/</Kbd>
      </div>
      <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" onKeyDown={onKeyDown}>
        <div className={cn("hidden gap-4 border-b border-line bg-surface-sunk/60 px-4 py-2.5 md:grid", LIBRARY_COLUMNS)}>
          <span className="eyebrow">Report</span>
          <span className="eyebrow hidden xl:block">Figures</span>
          <span className="eyebrow text-right">Headline</span>
          <span className="eyebrow">Status</span>
          <span className="eyebrow hidden xl:block">Added</span>
        </div>
        {shown === null ? (
          <ul>
            {Array.from({ length: 4 }, (_, i) => (
              <li key={i} className="flex h-[3.9375rem] items-center gap-3 border-b border-line px-4 last:border-b-0">
                <Bone className="size-9 rounded-xl" />
                <div className="space-y-1.5">
                  <Bone className="h-3.5 w-48" />
                  <Bone className="h-3 w-32" />
                </div>
              </li>
            ))}
          </ul>
        ) : shown.length ? (
          <ul data-testid="report-list">
            {shown.map((c) => (
              <li key={c.id} className="border-b border-line last:border-b-0">
                <LibraryRow card={c} />
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex flex-col items-center gap-2 px-6 py-12 text-center" data-testid="dashboard-no-match">
            <Search aria-hidden className="size-5 text-ink-3" />
            <p className="text-[0.875rem] font-medium text-ink">No reports match “{query}”</p>
            <button
              type="button"
              onClick={() => setQuery("")}
              className="mt-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-[0.78125rem] font-medium text-ink hover:bg-surface-sunk"
            >
              Show all reports
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function LibraryRow({ card }: { card: ReportCard }) {
  const status = statusMeta(card.status);
  const lead = card.ratios.find((r) => r.value != null) ?? null;
  return (
    <RowLink card={card} reportRow className={cn("group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3", LIBRARY_COLUMNS)}>
      <span className="flex min-w-0 items-center gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-line bg-surface-sunk text-[0.8125rem] font-semibold uppercase text-ink-2">
          {card.title.charAt(0)}
        </span>
        <span className="min-w-0">
          <span className="flex items-center gap-2">
            <span className="truncate text-[0.875rem] font-medium text-ink">{card.title}</span>
            {card.is_sample ? <SampleTag /> : null}
          </span>
          <span className="block truncate text-[0.71875rem] text-ink-3">
            {card.period_label ? `FY ${card.period_label} · ` : ""}
            {DOCUMENT_TYPES[card.document_type] ?? card.document_type} · <span className="font-mono">{card.filename}</span>
          </span>
        </span>
      </span>
      <span className="hidden xl:block">
        {card.figures ? <MiniSettlement counts={card.figures} /> : <span className="text-[0.75rem] text-ink-3">Not read yet</span>}
      </span>
      <span className="hidden text-right md:block">
        {lead ? (
          <>
            <span className="num block text-[0.84375rem] font-semibold text-ink">{formatRatio(lead.value!, lead.unit)}</span>
            <span className="block truncate text-[0.6875rem] text-ink-3">{lead.label}</span>
          </>
        ) : (
          <span className="text-[0.75rem] text-ink-3">—</span>
        )}
      </span>
      <span className="flex flex-wrap items-center justify-end gap-1.5 md:justify-start">
        <Badge tone={status.tone} data-testid="report-row-status">
          <status.Icon aria-hidden className={cn(status.spinning && "animate-spin motion-reduce:animate-none")} />
          {status.label}
        </Badge>
        {card.open_review_items ? <Badge tone="review">{card.open_review_items} to review</Badge> : null}
      </span>
      <span className="hidden items-center justify-between text-[0.75rem] text-ink-3 xl:flex">
        {whenAdded(card.created_at)}
        <ArrowRight aria-hidden className="size-4 -translate-x-1 opacity-0 transition-[opacity,translate] duration-150 group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:opacity-100" />
      </span>
    </RowLink>
  );
}

function MiniSettlement({ counts }: { counts: NonNullable<ReportCard["figures"]> }) {
  const total = counts.read + counts.derived + counts.manual + counts.empty;
  const settled = counts.read + counts.derived + counts.manual;
  return (
    <span className="block space-y-1" aria-label={`${settled} of ${total} figures settled, ${counts.empty} left empty`}>
      <span className="flex h-1.5 overflow-hidden rounded-full bg-ink/[0.06]">
        {SEGMENTS.map((s) =>
          counts[s.key] ? <span key={s.key} className={s.className} style={{ width: `${(counts[s.key] / total) * 100}%` }} /> : null,
        )}
      </span>
      <span className="num block text-[0.6875rem] text-ink-3">
        {settled} of {total} settled{counts.empty ? ` · ${counts.empty} empty` : ""}
      </span>
    </span>
  );
}

/** A report row: a link with hover/focus prefetch, an immediate press, and a context menu. */
function RowLink({
  card,
  className,
  children,
  reportRow = false,
}: {
  card: ReportCard;
  className?: string;
  children: React.ReactNode;
  reportRow?: boolean;
}) {
  const router = useRouter();
  const prefetch = usePrefetchReport();
  const toast = useToast();
  const [menu, setMenu] = React.useState<{ x: number; y: number } | null>(null);
  const href = `/reports/${card.id}`;
  const items: MenuItem[] = [
    { label: "Open", hint: "↵", icon: <ExternalLink aria-hidden />, run: () => router.push(href) },
    { label: "Open in a new tab", icon: <ExternalLink aria-hidden />, run: () => window.open(href, "_blank", "noopener") },
    {
      label: "Copy link",
      icon: <Link2 aria-hidden />,
      run: () => {
        void navigator.clipboard?.writeText(new URL(href, window.location.href).href);
        toast({ tone: "ok", title: "Link copied", body: card.title });
      },
    },
    { label: `Copy report number (${card.id})`, icon: <Copy aria-hidden />, run: () => void navigator.clipboard?.writeText(String(card.id)) },
  ];
  return (
    <>
      <a
        href={href}
        data-report-row={reportRow || undefined}
        data-testid={reportRow ? "report-row" : undefined}
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
          e.preventDefault();
          router.push(href);
        }}
        onPointerEnter={() => prefetch(card.id)}
        onFocus={() => prefetch(card.id)}
        onContextMenu={(e) => {
          e.preventDefault();
          setMenu({ x: e.clientX, y: e.clientY });
        }}
        className={cn(
          "outline-none transition-colors duration-100 hover:bg-surface-sunk/70 focus-visible:bg-accent-soft/60 active:bg-surface-sunk active:duration-0",
          className,
        )}
      >
        {children}
      </a>
      <ContextMenu at={menu} items={items} onClose={() => setMenu(null)} />
    </>
  );
}

// ---------------------------------------------------------------------------- samples

export function SampleTag() {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-suggested-line bg-suggested-soft px-1.5 py-px text-[0.65625rem] font-medium text-suggested"
      data-testid="sample-tag"
    >
      <FlaskConical aria-hidden className="size-3" />
      Sample
    </span>
  );
}

const sampleNotices = (toast: ReturnType<typeof useToast>) => ({
  added: (r: { added: number[] }) =>
    toast({ tone: "ok", title: "Sample reports added", body: `${r.added.length} being read; each appears as its stages finish.` }),
  removed: (r: { removed: number[] }) =>
    toast({ tone: "ok", title: "Sample reports removed", body: `${r.removed.length} removed. Your own reports are untouched.` }),
  failed: (what: "add" | "remove", e: Error) =>
    toast({ tone: "error", title: what === "add" ? "Sample reports weren’t added" : "Sample reports weren’t removed", body: e.message }),
});

/** Add the sample reports: bundled PDFs read by this pipeline, marked "Sample". */
function AddSamples() {
  const toast = useToast();
  const { add } = useSamples(sampleNotices(toast));
  return (
    <Tooltip content="Reports read by this pipeline, marked “Sample”: a bank, and reports waiting on a unit or a type">
      <button
        type="button"
        data-testid="samples-add"
        disabled={add.isPending}
        onClick={() => add.mutate()}
        className="inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[0.8125rem] text-ink-3 hover:bg-ink/[0.05] hover:text-ink-2 disabled:opacity-60"
      >
        {add.isPending ? <Loader aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : <FlaskConical aria-hidden className="size-4" />}
        {add.isPending ? "Adding samples…" : "Add sample reports"}
      </button>
    </Tooltip>
  );
}

/** Show/hide the sample reports (remembered), or remove them (they can be added again). */
function SampleControls() {
  const [show, setShow] = useShowSamples();
  const toast = useToast();
  const { remove } = useSamples(sampleNotices(toast));
  return (
    <div className="inline-flex h-9 items-center gap-0.5 rounded-lg border border-suggested-line bg-suggested-soft p-0.5 text-[0.78125rem]" data-testid="sample-controls">
      <span className="inline-flex items-center gap-1.5 px-2 font-medium text-suggested">
        <FlaskConical aria-hidden className="size-3.5" />
        Sample data
      </span>
      <Tooltip content={show ? "Hide the sample reports" : "Show the sample reports"}>
        <button
          type="button"
          onClick={() => setShow(!show)}
          aria-pressed={!show}
          aria-label={show ? "Hide sample reports" : "Show sample reports"}
          data-testid="samples-toggle"
          className="inline-flex size-8 items-center justify-center rounded-md text-suggested hover:bg-surface/70"
        >
          {show ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
        </button>
      </Tooltip>
      <Tooltip content="Remove the sample reports (you can add them again)">
        <button
          type="button"
          aria-label="Remove sample reports"
          data-testid="samples-remove"
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
          className="inline-flex size-8 items-center justify-center rounded-md text-suggested hover:bg-surface/70"
        >
          <Trash2 aria-hidden className="size-4" />
        </button>
      </Tooltip>
    </div>
  );
}

// ---------------------------------------------------------------------------- first run

const PROMISES = [
  { Icon: FileCheck2, title: "Figures from the statements", body: "Read from the income statement and balance sheet, checked by arithmetic, each with its page." },
  { Icon: Calculator, title: "Ratios computed in code", body: "Locked definitions, year-end balances, every input shown. Never written by a model." },
  { Icon: Quote, title: "Commentary that cites", body: "Every sentence carries a quote that code found in the report, one click from its page." },
];

function Onboarding({ unavailable }: { unavailable: boolean }) {
  const upload = useUpload();
  const toast = useToast();
  const { add } = useSamples(sampleNotices(toast));
  const loadSamples = () => add.mutate();
  return (
    <div className="flex flex-1 flex-col">
      <main className="relative flex-1" data-testid="onboarding">
        <div aria-hidden className="hero-grid pointer-events-none absolute inset-x-0 top-0 h-[32.5rem]" />
        <div className="relative mx-auto grid max-w-[1200px] grid-cols-1 items-center gap-12 px-4 pb-16 pt-12 sm:px-6 lg:grid-cols-[minmax(0,1fr)_460px] lg:px-8 lg:pt-16">
          <div className="space-y-9">
            <div className="space-y-5">
              <p className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[0.75rem] font-medium text-ink-2 shadow-[var(--shadow-card)]">
                <span aria-hidden className="size-1.5 rounded-full bg-ok" />
                UK annual reports · digitally born PDFs
              </p>
              <h1 className="max-w-xl text-[2.5rem] font-semibold leading-[1.05] sm:text-[3.125rem]">Financial Report Intelligence</h1>
              <p className="max-w-xl text-[1rem] leading-relaxed text-ink-2">
                Drop in an annual report. You get its figures read from the statements and anchored to their page, ratios
                computed in code, and commentary that cites its source. What can’t be verified stays empty, with the reason.
              </p>
              <div className="flex flex-wrap items-center gap-2.5">
                <button
                  type="button"
                  onClick={upload.pick}
                  className="inline-flex h-10 items-center gap-2 rounded-xl bg-ink px-4 text-[0.875rem] font-medium text-ink-inverse shadow-[var(--shadow-raised)] hover:opacity-90"
                >
                  <Plus aria-hidden className="size-4" />
                  Analyse your first report
                </button>
                {!unavailable ? (
                  <button
                    type="button"
                    onClick={loadSamples}
                    disabled={add.isPending}
                    data-testid="samples-add"
                    className="inline-flex h-10 items-center gap-2 rounded-xl border border-suggested-line bg-suggested-soft px-3.5 text-[0.84375rem] font-medium text-suggested disabled:opacity-60"
                  >
                    {add.isPending ? (
                      <Loader aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
                    ) : (
                      <FlaskConical aria-hidden className="size-4" />
                    )}
                    {add.isPending ? "Adding sample reports…" : "Explore with sample reports"}
                  </button>
                ) : null}
              </div>
              {!unavailable ? (
                <p className="max-w-xl text-[0.75rem] leading-relaxed text-ink-3">
                  Samples are reports read by this pipeline, not made-up numbers: a FTSE company’s statements, a bank, and
                  reports waiting on a unit or a document type. They’re marked “Sample” and can be hidden or removed.
                </p>
              ) : null}
            </div>
            <ul className="grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3">
              {PROMISES.map(({ Icon, title, body }) => (
                <li key={title} className="space-y-2 bg-surface p-5">
                  <span className="inline-flex size-8 items-center justify-center rounded-lg bg-accent-soft">
                    <Icon aria-hidden className="size-4 text-accent" />
                  </span>
                  <p className="text-[0.84375rem] font-semibold text-ink">{title}</p>
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

/** A placeholder block with the exact size of what it stands for. */
function Bone({ className }: { className?: string }) {
  return <span aria-hidden className={cn("block animate-pulse rounded bg-ink/[0.07] motion-reduce:animate-none", className)} />;
}

"use client";

import { ChevronRight, FileText, Info, RefreshCw, ShieldAlert } from "lucide-react";
import * as React from "react";
import { useReportContext } from "@/components/report/context";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import type { Citation, Figure, Paragraph, RatioName, Topic } from "@/lib/types";

const TOPIC_TITLES: Record<string, string> = {
  revenue_drivers: "Income drivers",
  strategic_risks: "Strategic risks",
  governance_and_directors: "Governance and directors’ notes",
  liquidity_and_capital: "Liquidity and capital",
};

/** Commentary (UI.md section 7). Every paragraph is validated by code before it reaches here. */
export function CommentaryPanel() {
  const { commentary, report } = useReportContext();
  if (!commentary) {
    const job = report.jobs.find((j) => j.stage === "commentary");
    return (
      <Card className="px-5 py-4" data-testid="commentary-pending">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em]">Commentary</h2>
        <p className="mt-1 text-[13px] text-ink-2">
          {job?.status === "failed"
            ? "Commentary could not be written for this report."
            : report.status === "ready"
              ? "No commentary for this report."
              : "Commentary is written once the figures are settled."}
        </p>
      </Card>
    );
  }
  const output = commentary.output;
  const summary = output.executive_summary;
  return (
    <section aria-labelledby="commentary-heading" className="space-y-4" data-testid="commentary">
      <SectionHeading
        id="commentary-heading"
        eyebrow="From the narrative"
        title="Commentary"
        className="mb-0"
        description={
          output.mode === "extractive"
            ? "Verbatim passages from the report, each with its page."
            : "Figures are filled in by code; quotes are checked against the report."
        }
        aside={
          output.mode === "extractive" ? (
            <Badge tone="neutral" data-testid="extractive-label">
              <FileText aria-hidden />
              {output.label ?? "Extractive summary: no generated text"}
            </Badge>
          ) : null
        }
      />

      {commentary.stale || report.stale ? (
        <div
          role="status"
          data-testid="commentary-stale"
          className="flex items-start gap-2.5 rounded-xl border border-amber-line bg-amber-soft px-4 py-3"
        >
          <RefreshCw aria-hidden className="mt-0.5 size-4 shrink-0 text-amber" />
          <div className="text-[12.5px] leading-relaxed text-ink-2">
            <p className="text-[13px] font-semibold text-ink">Figures changed since this commentary was written</p>
            It describes an earlier version of the figures (pack {output.statement_pack_sha.slice(0, 12)}; now{" "}
            {report.pack_sha?.slice(0, 12)}). Figures in the table and the ratio cards are current.
          </div>
        </div>
      ) : null}

      {summary.status === "ok" && summary.bullets.length ? (
        <Card className="px-5 py-4" data-testid="executive-summary">
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-3">Executive summary</h3>
          <ul className="mt-2 space-y-2">
            {summary.bullets.map((b, i) => (
              <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed text-ink">
                <span aria-hidden className="mt-[9px] size-1 shrink-0 rounded-full bg-ink-3" />
                <ParagraphText paragraph={b} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {output.topics.map((t) => (
        <TopicPanel key={t.topic} topic={t} />
      ))}
    </section>
  );
}

function TopicPanel({ topic }: { topic: Topic }) {
  const title = TOPIC_TITLES[topic.topic] ?? topic.topic;
  const [open, setOpen] = React.useState(false);
  if (topic.status === "omitted") {
    return (
      <Card className="px-5 py-3" data-testid="topic-state-omitted" data-topic={topic.topic}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex w-full items-center gap-1.5 text-left text-[13px] text-ink-2"
        >
          <ChevronRight aria-hidden className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          <span className="font-medium text-ink">{title}</span>
          <span className="text-ink-3">· No liquidity or capital evidence retrieved.</span>
        </button>
        {open && topic.reason ? <p className="mt-1 pl-5 text-[12.5px] text-ink-3">{topic.reason}</p> : null}
      </Card>
    );
  }
  return (
    <Card className="px-5 py-4" data-testid={`topic-state-${topic.status}`} data-topic={topic.topic}>
      <h3 className="text-[13px] font-semibold text-ink">{title}</h3>
      {topic.status === "insufficient_evidence" ? (
        <p className="mt-1.5 flex items-center gap-1.5 text-[13px] text-ink-2">
          <Info aria-hidden className="size-4 text-ink-3" />
          There isn’t enough in the report to comment on this topic.
        </p>
      ) : topic.status === "validation_failed" ? (
        <Tooltip content={topic.reason ? `Why: ${topic.reason.split(": ").slice(1).join(": ") || topic.reason}.` : null}>
          <p tabIndex={0} className="mt-1.5 flex items-center gap-1.5 text-[13px] text-ink-2" data-testid="validation-failed-text">
            <ShieldAlert aria-hidden className="size-4 shrink-0 text-review" />
            Commentary withheld: it failed evidence checks{removedText(topic)}.
          </p>
        </Tooltip>
      ) : (
        <div className="mt-2 space-y-3">
          {topic.paragraphs.map((p, i) => (
            <p key={i} className="text-[13.5px] leading-relaxed text-ink">
              <ParagraphText paragraph={p} />
            </p>
          ))}
        </div>
      )}
    </Card>
  );
}

/** " (2 paragraphs removed)" from the validator's reason; nothing when no paragraph was usable. */
function removedText(topic: Topic): string {
  const m = /^(\d+) paragraphs? removed/.exec(topic.reason ?? "");
  if (!m) return "";
  const n = Number(m[1]);
  return ` (${n} paragraph${n === 1 ? "" : "s"} removed)`;
}

/** The rendered text with code-rendered figures underlined and citation markers appended. */
function ParagraphText({ paragraph }: { paragraph: Paragraph }) {
  const figures = paragraph.figures.filter((f): f is Figure & { rendered: string } => Boolean(f.rendered));
  const parts = splitFigures(paragraph.rendered, figures);
  return (
    <span>
      {parts.map((part, i) =>
        part.figure ? (
          <FigureLink key={i} figure={part.figure} text={part.text} />
        ) : (
          <React.Fragment key={i}>{part.text}</React.Fragment>
        ),
      )}
      {paragraph.citations.map((c, i) => (
        <CitationMarker key={c.citation_id} citation={c} n={i + 1} />
      ))}
    </span>
  );
}

type Part = { text: string; figure: (Figure & { rendered: string }) | null };

function splitFigures(text: string, figures: (Figure & { rendered: string })[]): Part[] {
  if (!figures.length) return [{ text, figure: null }];
  // Figures outside quotation marks only: a quoted figure is the company's text, not ours.
  const byText = new Map(figures.map((f) => [f.rendered, f]));
  const ordered = [...byText.keys()].sort((a, b) => b.length - a.length);
  const pattern = new RegExp(ordered.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
  const out: Part[] = [];
  let last = 0;
  let scanned = 0;
  let inQuote = false;
  for (const m of text.matchAll(pattern)) {
    const at = m.index ?? 0;
    for (let j = scanned; j < at; j++) {
      const ch = text[j];
      if (ch === "“") inQuote = true;
      else if (ch === "”") inQuote = false;
      else if (ch === '"') inQuote = !inQuote;
    }
    scanned = at;
    if (inQuote) continue;
    if (at > last) out.push({ text: text.slice(last, at), figure: null });
    out.push({ text: m[0], figure: byText.get(m[0]) ?? null });
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), figure: null });
  return out;
}

/** A code-rendered figure. Clicking selects its source: the figure, the ratio, or the pages. */
function FigureLink({ figure, text }: { figure: Figure; text: string }) {
  const { select, focusRatio, report } = useReportContext();
  const open = () => {
    const parts = figure.placeholder.split(":");
    const [kind] = parts;
    if (kind === "item" || kind === "exact") {
      select({ kind: "figure", item: parts[1]!, period: parts[2]! });
    } else if (kind === "change" && parts[1] === "item") {
      select({ kind: "figure", item: parts[2]!, period: parts[4]! });
    } else if (kind === "ratio" || (kind === "change" && parts[1] === "ratio")) {
      const name = kind === "ratio" ? parts[1]! : parts[2]!;
      const period = kind === "ratio" ? parts[2]! : parts[4]!;
      focusRatio(name);
      const ratio = report.ratios?.periods.find((p) => p.period_id === period)?.ratios[name as RatioName];
      const input = ratio ? Object.values(ratio.inputs).find((i) => i.page) : undefined;
      if (input) select({ kind: "input", ratio: name, item: input.item, period });
    } else {
      select({
        kind: "pages",
        label: text,
        pages: figure.pages,
        note: "A figure from the report’s own text (for example earnings per share or free cash flow), read by code from the printed pages. It never feeds a ratio.",
      });
    }
  };
  return (
    <button
      type="button"
      onClick={open}
      data-testid="placeholder-figure"
      data-placeholder={figure.placeholder}
      className="placeholder-figure num cursor-pointer rounded-sm hover:bg-accent-soft hover:text-accent"
    >
      {text}
    </button>
  );
}

function CitationMarker({ citation, n }: { citation: Citation; n: number }) {
  const { select, selection } = useReportContext();
  const where = citation.heading_path.slice(1).join(" › ");
  const folio = citation.page_label ? ` · printed p. ${citation.page_label}` : "";
  const active = selection?.kind === "citation" && selection.citation === citation;
  return (
    <Tooltip
      content={
        <>
          <span className="font-medium text-ink">PDF p.&nbsp;{citation.page}{folio}</span>
          {where ? <><br />{where}</> : null}
        </>
      }
    >
      <button
        type="button"
        data-testid="citation-marker"
        data-page={citation.page}
        aria-pressed={active}
        onClick={() => select({ kind: "citation", citation, n })}
        className={cn(
          "num ml-0.5 inline-flex h-4 min-w-4 -translate-y-1.5 items-center justify-center rounded border px-1 align-baseline text-[10px] font-semibold",
          active ? "border-accent bg-accent text-ink-inverse" : "border-line bg-surface text-accent hover:border-accent",
        )}
        aria-label={`Citation ${n}: PDF page ${citation.page}`}
      >
        {n}
      </button>
    </Tooltip>
  );
}

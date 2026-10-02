"use client";

import { ChevronRight, FileText, Info, ShieldAlert } from "lucide-react";
import * as React from "react";
import { useReportContext } from "@/components/report/context";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import type { Citation, Paragraph, Topic } from "@/lib/types";

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
    <section aria-labelledby="commentary-heading" className="space-y-3" data-testid="commentary">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="commentary-heading" className="text-[15px] font-semibold tracking-[-0.01em]">
          Commentary
        </h2>
        {output.mode === "extractive" ? (
          <Badge tone="neutral" data-testid="extractive-label">
            <FileText aria-hidden />
            {output.label ?? "Extractive summary: no generated text"}
          </Badge>
        ) : (
          <p className="text-xs text-ink-3">Figures are filled in by code; quotes are checked against the report.</p>
        )}
      </div>

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
        <Tooltip content={topic.reason}>
          <p tabIndex={0} className="mt-1.5 flex items-center gap-1.5 text-[13px] text-ink-2">
            <ShieldAlert aria-hidden className="size-4 text-review" />
            Commentary withheld: it failed evidence checks ({removedCount(topic)} paragraphs removed).
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

function removedCount(topic: Topic): number {
  const m = /(\d+)/.exec(topic.reason ?? "");
  return m ? Number(m[1]) : topic.paragraphs.length;
}

/** The rendered text with code-rendered figures underlined and citation markers appended. */
function ParagraphText({ paragraph }: { paragraph: Paragraph }) {
  const figures = paragraph.figures
    .map((f) => f.rendered)
    .filter((r): r is string => Boolean(r))
    .sort((a, b) => b.length - a.length);
  const parts = splitFigures(paragraph.rendered, figures);
  return (
    <span>
      {parts.map((part, i) =>
        part.figure ? (
          <span key={i} className="placeholder-figure num" data-testid="placeholder-figure">
            {part.text}
          </span>
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

function splitFigures(text: string, figures: string[]): { text: string; figure: boolean }[] {
  if (!figures.length) return [{ text, figure: false }];
  // Figures outside quotation marks only: a quoted figure is the company's text, not ours.
  const out: { text: string; figure: boolean }[] = [];
  const pattern = new RegExp(figures.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
  let last = 0;
  let inQuote = false;
  const quoteAt = (i: number) => {
    for (let j = last; j < i; j++) if (text[j] === "“" || text[j] === "”" || text[j] === '"') inQuote = !inQuote;
  };
  for (const m of text.matchAll(pattern)) {
    const at = m.index ?? 0;
    quoteAt(at);
    if (inQuote) continue;
    if (at > last) out.push({ text: text.slice(last, at), figure: false });
    out.push({ text: m[0], figure: true });
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), figure: false });
  return out;
}

function CitationMarker({ citation, n }: { citation: Citation; n: number }) {
  const where = citation.heading_path.slice(1).join(" › ");
  const folio = citation.page_label ? ` · printed p. ${citation.page_label}` : "";
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
        className="num ml-0.5 inline-flex h-4 min-w-4 -translate-y-1.5 items-center justify-center rounded border border-line bg-surface px-1 align-baseline text-[10px] font-semibold text-accent hover:border-accent"
        aria-label={`Citation ${n}: PDF page ${citation.page}`}
      >
        {n}
      </button>
    </Tooltip>
  );
}

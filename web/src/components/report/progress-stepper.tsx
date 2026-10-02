"use client";

import { Check, CircleDashed, Loader2, RotateCcw, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Job, Report } from "@/lib/types";

/** UI.md section 3: the steps a person sees, each driven by one worker stage (jobs table). */
const STEPS: { label: string; stage: string }[] = [
  { label: "Reading pages", stage: "text_layer" },
  { label: "Finding statements", stage: "extract" },
  { label: "Extracting figures", stage: "extract" },
  { label: "Checking", stage: "extract" },
  { label: "Calculating ratios", stage: "ratios" },
  { label: "Indexing narrative", stage: "index" },
  { label: "Writing commentary", stage: "commentary" },
];

type StepState = "done" | "running" | "fallback" | "failed" | "waiting";

function stateOf(job: Job | undefined, first: boolean, report: Report): StepState {
  if (!job) return "waiting";
  if (job.status === "done") return "done";
  if (job.status === "failed") return "failed";
  if (job.status === "running") return job.attempts > 1 ? "fallback" : "running";
  // queued: the first queued stage of a moving report is the one about to run
  if (job.attempts > 0) return "fallback"; // waiting to retry after a failure
  return first && (report.status === "processing" || report.status === "queued") ? "running" : "waiting";
}

/** Stages finish independently, so figures appear before commentary (UI.md section 3). */
export function ProgressStepper({ report }: { report: Report }) {
  const jobs = new Map(report.jobs.map((j) => [j.stage, j]));
  const firstOpen = report.jobs.find((j) => j.status !== "done")?.stage;
  const ingest = jobs.get("ingest");
  return (
    <section aria-labelledby="progress-heading" className="rounded-xl border border-line bg-surface px-5 py-4" data-testid="progress-stepper">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="progress-heading" className="text-[13px] font-semibold text-ink">
          Reading the report
        </h2>
        <p className="text-[12px] text-ink-3" aria-live="polite" data-testid="progress-summary">
          {report.jobs.filter((j) => j.status === "done").length} of {report.jobs.length} stages done
        </p>
      </div>
      <ol className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {STEPS.map((step) => {
          const job = step.label === "Reading pages" && ingest?.status !== "done" ? ingest : jobs.get(step.stage);
          const state = stateOf(job, job?.stage === firstOpen, report);
          return (
            <li
              key={step.label}
              data-testid="progress-step"
              data-step={step.label}
              data-state={state}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-2.5 py-2 text-[12px]",
                state === "done" && "border-ok-line bg-ok-soft text-ok",
                state === "running" && "border-accent/40 bg-accent-soft text-accent",
                state === "fallback" && "border-amber-line bg-amber-soft text-amber",
                state === "failed" && "border-missing-line bg-missing-soft text-missing",
                state === "waiting" && "border-line bg-surface-sunk text-ink-3",
              )}
            >
              {state === "done" ? (
                <Check aria-hidden className="size-3.5 shrink-0" />
              ) : state === "running" ? (
                <Loader2 aria-hidden className="size-3.5 shrink-0 animate-spin motion-reduce:animate-none" />
              ) : state === "fallback" ? (
                <RotateCcw aria-hidden className="size-3.5 shrink-0" />
              ) : state === "failed" ? (
                <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
              ) : (
                <CircleDashed aria-hidden className="size-3.5 shrink-0" />
              )}
              <span className="font-medium">{step.label}</span>
              <span className="sr-only">: {state === "fallback" ? "retrying" : state}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** Plain-English names for the worker's error classes (worker/stages.FAILURE_CLASS). */
export function failureSentence(report: Report): { stage: string; text: string; code: string } | null {
  const job = report.jobs.find((j) => j.status === "failed") ?? null;
  const code = job?.error_code ?? "";
  const stage = STEPS.find((s) => s.stage === job?.stage)?.label ?? job?.stage ?? "an early stage";
  const cls = code.split(":")[0];
  const text =
    cls === "parse"
      ? "The PDF couldn’t be read."
      : cls === "map"
        ? "The figures couldn’t be extracted or checked."
        : cls === "retrieve"
          ? "The narrative couldn’t be indexed."
          : cls === "generate"
            ? "The commentary couldn’t be written."
            : "Processing stopped.";
  if (!job && report.status !== "failed") return null;
  return { stage, text, code: code || report.status };
}


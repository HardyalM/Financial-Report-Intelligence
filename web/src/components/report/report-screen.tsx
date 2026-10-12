"use client";

import { CircleAlert } from "lucide-react";
import Link from "next/link";
import { BannerStack } from "@/components/report/banners";
import { CommentaryPanel } from "@/components/report/commentary";
import { ReportProvider } from "@/components/report/context";
import { EvidencePanel } from "@/components/report/evidence-panel";
import { FiguresTable } from "@/components/report/figures-table";
import { ReportFooter, SiteFooter } from "@/components/report/footer";
import { ReportHeader } from "@/components/report/header";
import { SectionNav } from "@/components/report/section-nav";
import { RatioCards } from "@/components/report/ratio-cards";
import { ReportedMetrics } from "@/components/report/reported-metrics";
import { failureSentence, ProgressStepper } from "@/components/report/progress-stepper";
import { NumbersSnapshot } from "@/components/report/snapshot";
import { UnitDialog } from "@/components/report/unit-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { inProgress, useReport } from "@/lib/api";
import type { Report } from "@/lib/types";

/** The one primary screen (UI.md section 2). */
export function ReportScreen({ id }: { id: string }) {
  const { state, reload } = useReport(id);
  if (state.status === "loading") return <LoadingScreen />;
  if (state.status === "error") {
    const { error } = state;
    const title =
      error.code === "report_not_found" || error.status === 404
        ? `There is no report ${id}`
        : error.status === 0
          ? "The API can’t be reached"
          : "This report couldn’t be loaded";
    return (
      <div className="flex min-h-screen flex-col">
        <main className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
          <CircleAlert aria-hidden className="size-6 text-ink-3" />
          <h1 className="text-lg font-semibold" data-testid="report-error">
            {title}
          </h1>
          <p className="text-sm text-ink-2">
            {error.message} <span className="font-mono text-xs text-ink-3">({error.code})</span>
          </p>
          <Link href="/" className="text-sm font-medium text-accent hover:underline">
            Back to the start
          </Link>
        </main>
        <SiteFooter />
      </div>
    );
  }
  return (
    <TooltipProvider delayDuration={250} skipDelayDuration={100}>
      <ReportProvider data={state.data} reload={reload}>
        <div className="flex min-h-screen flex-col">
          <ReportHeader />
          <div className="sticky top-14 z-30 border-b border-line bg-glass backdrop-blur-xl backdrop-saturate-150">
            <div className="mx-auto max-w-[1600px] px-1 sm:px-3 lg:px-5">
              <SectionNav />
            </div>
          </div>
          {state.data.report.status === "needs_unit_confirmation" ? <UnitDialog /> : null}
          <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-8 sm:px-6 lg:px-8">
            <StageStatus report={state.data.report} />
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_440px] 2xl:grid-cols-[minmax(0,1fr)_520px]">
              <div className="min-w-0 space-y-10">
                <div className="space-y-4 empty:hidden">
                  <BannerStack />
                  <NumbersSnapshot />
                </div>
                <div id="figures">
                  <FiguresTable />
                </div>
                <div id="ratios" className="space-y-10">
                  <RatioCards />
                  <ReportedMetrics />
                </div>
                <div id="commentary">
                  <CommentaryPanel />
                </div>
              </div>
              <div className="min-w-0">
                <EvidencePanel />
              </div>
            </div>
          </main>
          <ReportFooter />
        </div>
      </ReportProvider>
    </TooltipProvider>
  );
}

/** Processing (stepper) or failed (the error in words and the stage), UI.md section 3. */
function StageStatus({ report }: { report: Report }) {
  if (inProgress(report)) {
    return (
      <div className="mb-6">
        <ProgressStepper report={report} />
      </div>
    );
  }
  if (report.status !== "failed") return null;
  const failure = failureSentence(report);
  return (
    <div
      role="alert"
      data-testid="report-failed"
      className="mb-6 rounded-xl border border-missing-line bg-missing-soft px-5 py-4"
    >
      <p className="text-[14px] font-semibold text-ink">{failure?.text ?? "Processing stopped."}</p>
      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">
        It stopped at “{failure?.stage}” after its retries. Uploading the same file again shows this
        report; a different file starts afresh.{" "}
        <span className="font-mono text-[11.5px] text-ink-3">
          report {report.id} · {failure?.code}
        </span>
      </p>
      <div className="mt-3">
        <ProgressStepper report={report} />
      </div>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div className="min-h-screen" aria-busy="true" aria-live="polite">
      <div className="border-b border-line bg-surface px-8 py-7">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="mt-3 h-8 w-80" />
        <Skeleton className="mt-3 h-4 w-96" />
        <Skeleton className="mt-6 h-24 w-full rounded-2xl" />
      </div>
      <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-6 px-8 py-6 xl:grid-cols-[minmax(0,1fr)_440px] 2xl:grid-cols-[minmax(0,1fr)_520px]">
        <div className="space-y-4">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-96 w-full" />
          <div className="grid grid-cols-2 gap-3">
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
        </div>
        <Skeleton className="hidden h-80 xl:block" />
      </div>
      <span className="sr-only">Loading the report</span>
    </div>
  );
}

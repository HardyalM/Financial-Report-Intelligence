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
import { RatioCards } from "@/components/report/ratio-cards";
import { NumbersSnapshot } from "@/components/report/snapshot";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useReport } from "@/lib/api";

/** The one primary screen (UI.md section 2). */
export function ReportScreen({ id }: { id: string }) {
  const state = useReport(id);
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
      <ReportProvider data={state.data}>
        <div className="flex min-h-screen flex-col">
          <ReportHeader />
          <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
              <div className="min-w-0 space-y-6">
                <BannerStack />
                <NumbersSnapshot />
                <FiguresTable />
                <RatioCards />
                <CommentaryPanel />
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

function LoadingScreen() {
  return (
    <div className="min-h-screen" aria-busy="true" aria-live="polite">
      <div className="border-b border-line bg-surface px-8 py-5">
        <Skeleton className="h-5 w-64" />
        <Skeleton className="mt-3 h-4 w-96" />
      </div>
      <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-6 px-8 py-6 xl:grid-cols-[minmax(0,1fr)_400px]">
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

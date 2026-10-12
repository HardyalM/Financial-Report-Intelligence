"use client";
import Link from "next/link";
import type * as React from "react";

import { BrandMark } from "@/components/brand-mark";
import { useReportContext } from "@/components/report/context";

export function ReportFooter() {
  const { report, commentary } = useReportContext();
  const model = commentary?.model_id ?? (commentary ? "extractive (no model)" : null);
  const prompt = commentary?.prompt_version;
  const pipeline = report.pack?.source.pipeline_version;
  return (
    <SiteFooter>
      {model ? <span>Commentary: {model}{prompt ? ` · prompt ${prompt}` : ""}</span> : null}
      {pipeline ? <span>Pipeline {pipeline}</span> : null}
      {report.pack_sha ? <span>pack {report.pack_sha.slice(0, 12)}</span> : null}
    </SiteFooter>
  );
}

export function SiteFooter({ children }: { children?: React.ReactNode }) {
  return (
    <footer className="mt-16 border-t border-line bg-surface" data-testid="footer">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-3 px-4 py-6 text-xs text-ink-3 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="inline-flex items-center gap-2">
            <BrandMark className="size-5" />
            <span className="font-semibold text-ink-2">FinIntel</span>
          </span>
          <strong className="font-semibold text-ink-2">Research aid. Not investment advice.</strong>
          <Link href="/limitations" className="text-ink-2 underline-offset-2 hover:text-ink hover:underline" data-testid="limitations-link">
            Limitations
          </Link>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
          {children ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[0.6875rem] text-ink-3">{children}</div>
          ) : (
            <span />
          )}
          <p className="ml-auto text-[0.6875rem] tracking-[0.01em] text-ink-3/80" data-testid="signature">
            Designed and developed by: <span className="font-medium text-ink-2/90">Hardyal Mahal</span>
          </p>
        </div>
      </div>
    </footer>
  );
}

"use client";
import Link from "next/link";
import type * as React from "react";

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
      {report.pack_sha ? <span className="font-mono">pack {report.pack_sha.slice(0, 12)}</span> : null}
    </SiteFooter>
  );
}

export function SiteFooter({ children }: { children?: React.ReactNode }) {
  return (
    <footer className="mt-12 border-t border-line" data-testid="footer">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-5 text-xs text-ink-3 sm:px-6 lg:px-8">
        <strong className="font-semibold text-ink-2">Research aid. Not investment advice.</strong>
        <Link href="/limitations" className="text-ink-2 underline-offset-2 hover:text-ink hover:underline" data-testid="limitations-link">
          Limitations
        </Link>
        {children}
      </div>
    </footer>
  );
}

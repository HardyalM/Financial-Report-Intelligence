"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Menu, Plus, Search, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { Kbd } from "@/components/pdf/toolbar";
import { shortcutLabel } from "@/components/pdf/use-viewer-input";
import { usePalette } from "@/components/shell/command-palette";
import { reportTitle, statusMeta } from "@/components/shell/report-meta";
import { useShell } from "@/components/shell/shell-context";
import { useUpload } from "@/components/shell/upload";
import type { ReportData } from "@/lib/api";
import { cn } from "@/lib/cn";
import { keys, useReports } from "@/lib/queries";

/** The bar above every page: where you are (breadcrumbs), search, and one primary action. */
export function TopBar() {
  const pathname = usePathname() ?? "/";
  const { setDrawer } = useShell();
  const palette = usePalette();
  const upload = useUpload();
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-glass backdrop-blur-xl backdrop-saturate-150" data-testid="top-bar">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={() => setDrawer(true)}
          aria-label="Open navigation"
          className="-ml-1 flex size-8 items-center justify-center rounded-lg text-ink-2 hover:bg-ink/[0.05] lg:hidden"
        >
          <Menu aria-hidden className="size-[18px]" />
        </button>
        <Breadcrumbs pathname={pathname} />
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => palette.open()}
            data-testid="top-search"
            className="hidden h-8 w-64 items-center gap-2 rounded-lg border border-line bg-surface/80 pl-2.5 pr-1.5 text-[13px] text-ink-3 shadow-[var(--shadow-card)] transition-colors hover:border-line-strong hover:text-ink-2 md:flex"
          >
            <Search aria-hidden className="size-[15px]" />
            <span className="flex-1 text-left">Search or jump to…</span>
            <Kbd>{shortcutLabel("mod+k")}</Kbd>
          </button>
          <button type="button" onClick={() => palette.open()} aria-label="Search" className="flex size-8 items-center justify-center rounded-lg text-ink-2 hover:bg-ink/[0.05] md:hidden">
            <Search aria-hidden className="size-[17px]" />
          </button>
          <span className="hidden items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[11.5px] font-medium text-ink-2 xl:inline-flex">
            <ShieldCheck aria-hidden className="size-3.5 text-ok" />
            Research aid · not investment advice
          </span>
          <button
            type="button"
            onClick={upload.pick}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-ink px-3 text-[13px] font-medium text-ink-inverse shadow-[var(--shadow-card)] transition-[opacity,transform] hover:opacity-90 active:scale-[0.98]"
          >
            <Plus aria-hidden className="size-4" />
            <span className="hidden sm:inline">New report</span>
          </button>
        </div>
      </div>
    </header>
  );
}

function Breadcrumbs({ pathname }: { pathname: string }) {
  const reports = useReports();
  const client = useQueryClient();
  const id = /^\/reports\/(\d+)/.exec(pathname)?.[1];
  const crumbs: { label: string; href?: string; extra?: React.ReactNode }[] = [{ label: "Dashboard", href: "/" }];
  if (pathname === "/limitations") crumbs.push({ label: "Method & limits" });
  if (id) {
    const summary = reports.data?.find((r) => String(r.id) === id);
    const cached = client.getQueryData<ReportData>(keys.report(id))?.report;
    const name = summary
      ? reportTitle(summary)
      : cached
        ? (cached.pack?.company_name ?? cached.filename.replace(/\.pdf$/i, ""))
        : `Report ${id}`;
    const status = statusMeta(summary?.status ?? cached?.status ?? "");
    crumbs.push({
      label: name,
      extra: summary || cached ? (
        <span className="ml-2 hidden items-center gap-1.5 text-[12px] text-ink-3 sm:inline-flex">
          <span aria-hidden className={cn("size-1.5 rounded-full", status.dot)} />
          {status.label}
        </span>
      ) : null,
    });
  }
  return (
    <nav aria-label="Breadcrumb" className="min-w-0" data-testid="breadcrumbs">
      <ol className="flex min-w-0 items-center gap-1 text-[13px]">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <li key={c.label} className={cn("flex min-w-0 items-center gap-1", !last && "shrink-0")}>
              {i > 0 ? <ChevronRight aria-hidden className="size-3.5 shrink-0 text-ink-3/70" /> : null}
              {c.href && !last ? (
                <Link href={c.href} className="rounded-md px-1.5 py-1 text-ink-3 transition-colors hover:bg-ink/[0.05] hover:text-ink">
                  {c.label}
                </Link>
              ) : (
                <span aria-current={last ? "page" : undefined} className="flex min-w-0 items-center truncate px-1.5 py-1 font-medium text-ink">
                  <span className="truncate">{c.label}</span>
                  {c.extra}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

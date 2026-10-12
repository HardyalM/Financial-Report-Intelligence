import { Plus, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type * as React from "react";

/** The product mark: a ledger page with a verified rule, drawn in the brand colours. */
export function BrandMark({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect x="1" y="1" width="30" height="30" rx="8" className="fill-brand" />
      <path d="M9 10.5h14M9 15.5h9M9 20.5h11" className="stroke-ink-inverse" strokeWidth="2" strokeLinecap="round" />
      <circle cx="22.5" cy="20.5" r="3.25" className="fill-brand-2 stroke-brand" strokeWidth="1.5" />
    </svg>
  );
}

/**
 * The sticky top bar on every page: the product, where you are, and the one standing reminder
 * that this is a research aid (UI.md section 1.6).
 */
export function AppBar({ children }: { children?: React.ReactNode }) {
  return (
    <div className="sticky top-0 z-40 border-b border-line bg-glass backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 rounded-md" aria-label="FinIntel home">
          <BrandMark />
          <span className="text-[15px] font-semibold tracking-[-0.02em] text-ink">
            FinIntel
          </span>
        </Link>
        {children ? (
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-[13px] text-ink-3">
            <span aria-hidden className="text-line-strong">
              /
            </span>
            {children}
          </nav>
        ) : null}
        <div className="ml-auto flex items-center gap-1.5">
          <span className="hidden items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[11.5px] font-medium text-ink-2 md:inline-flex">
            <ShieldCheck aria-hidden className="size-3.5 text-ok" />
            Research aid · not investment advice
          </span>
          <Link
            href="/limitations"
            className="hidden rounded-md px-2.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:bg-surface-sunk hover:text-ink sm:inline-flex"
          >
            Method & limits
          </Link>
          <Link
            href="/"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-ink px-3 text-[13px] font-medium text-ink-inverse shadow-[var(--shadow-card)] transition-opacity hover:opacity-90"
          >
            <Plus aria-hidden className="size-4" />
            <span className="hidden sm:inline">New report</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

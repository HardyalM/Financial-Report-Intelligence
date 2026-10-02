import { FileSearch } from "lucide-react";
import { SiteFooter } from "@/components/report/footer";
import { OpenReport } from "./open-report";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-4 py-16">
        <div className="space-y-3">
          <span className="inline-flex size-10 items-center justify-center rounded-xl border border-line bg-surface shadow-[var(--shadow-card)]">
            <FileSearch aria-hidden className="size-5 text-accent" />
          </span>
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">Financial Report Intelligence</h1>
          <p className="text-[15px] leading-relaxed text-ink-2">
            Figures read from the statements and checked by arithmetic, ratios computed in code, and
            commentary that cites the page it comes from. When a figure can’t be verified, it stays
            empty and says why.
          </p>
        </div>
        <OpenReport />
      </main>
      <SiteFooter />
    </div>
  );
}

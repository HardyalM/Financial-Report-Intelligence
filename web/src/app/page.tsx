import { Calculator, FileCheck2, Quote } from "lucide-react";
import { AppBar } from "@/components/app-bar";
import { SiteFooter } from "@/components/report/footer";
import { OpenReport } from "./open-report";
import { UploadDropzone } from "./upload-dropzone";

const PROMISES = [
  {
    Icon: FileCheck2,
    title: "Figures from the statements",
    body: "Read from the income statement and balance sheet, checked by arithmetic, each with its page.",
  },
  {
    Icon: Calculator,
    title: "Ratios computed in code",
    body: "Locked definitions, year-end balances, every input shown. Never written by a model.",
  },
  {
    Icon: Quote,
    title: "Commentary that cites",
    body: "Every sentence carries a quote that code found in the report, one click from its page.",
  },
];

const STAGES = [
  "Reading pages",
  "Finding statements",
  "Extracting figures",
  "Checking",
  "Calculating ratios",
  "Indexing narrative",
  "Writing commentary",
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <AppBar />
      <main className="relative flex-1">
        <div aria-hidden className="hero-grid pointer-events-none absolute inset-x-0 top-0 h-[560px]" />
        <div className="relative mx-auto grid max-w-[1200px] grid-cols-1 gap-12 px-4 pb-16 pt-14 sm:px-6 lg:grid-cols-[minmax(0,1fr)_480px] lg:gap-16 lg:px-8 lg:pt-20">
          <div className="space-y-10">
            <div className="space-y-5">
              <p className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[12px] font-medium text-ink-2 shadow-[var(--shadow-card)]">
                <span aria-hidden className="size-1.5 rounded-full bg-ok" />
                UK annual reports · digitally born PDFs
              </p>
              <h1 className="max-w-xl text-[40px] font-semibold leading-[1.05] tracking-[-0.035em] text-ink sm:text-[52px]">
                Financial Report Intelligence
              </h1>
              <p className="max-w-xl text-[16px] leading-relaxed text-ink-2">
                Figures read from the statements and checked by arithmetic, ratios computed in code, and
                commentary that cites the page it comes from. When a figure can’t be verified, it stays
                empty and says why.
              </p>
            </div>

            <ul className="grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3">
              {PROMISES.map(({ Icon, title, body }) => (
                <li key={title} className="space-y-2 bg-surface p-5">
                  <span className="inline-flex size-8 items-center justify-center rounded-lg bg-accent-soft">
                    <Icon aria-hidden className="size-4 text-accent" />
                  </span>
                  <p className="text-[13.5px] font-semibold tracking-[-0.01em] text-ink">{title}</p>
                  <p className="text-[12.5px] leading-relaxed text-ink-3">{body}</p>
                </li>
              ))}
            </ul>

            <div className="space-y-3">
              <p className="eyebrow">What happens to a report</p>
              <ol className="flex flex-wrap gap-x-1 gap-y-2 text-[12.5px] text-ink-2">
                {STAGES.map((stage, i) => (
                  <li key={stage} className="inline-flex items-center gap-1">
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1">
                      <span className="num text-[11px] text-ink-3">{i + 1}</span>
                      {stage}
                    </span>
                    {i < STAGES.length - 1 ? (
                      <span aria-hidden className="text-line-strong">
                        →
                      </span>
                    ) : null}
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div className="lg:pt-6">
            <div className="space-y-5 rounded-3xl border border-line bg-surface p-5 shadow-[var(--shadow-pop)] sm:p-6">
              <div className="space-y-1">
                <p className="eyebrow">Start</p>
                <h2 className="text-[18px] font-semibold tracking-[-0.02em] text-ink">Analyse a report</h2>
              </div>
              <UploadDropzone />
              <div className="space-y-2 border-t border-line pt-5">
                <p className="text-[12.5px] text-ink-3">Or open a report already read:</p>
                <OpenReport />
              </div>
            </div>
            <p className="mt-4 px-2 text-[11.5px] leading-relaxed text-ink-3">
              Figures and ratios are computed locally. Commentary uses the model provider you configured, if any.
            </p>
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

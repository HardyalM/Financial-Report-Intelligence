import type { Metadata } from "next";
import Link from "next/link";
import { AppBar } from "@/components/app-bar";
import { SiteFooter } from "@/components/report/footer";

export const metadata: Metadata = { title: "Limitations" };

/** What this tool does not do, said plainly (UI.md section 1: the only page besides the report). */
export default function Limitations() {
  return (
    <div className="flex min-h-screen flex-col">
      <AppBar />
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-12 sm:px-6" data-testid="limitations">
        <Link href="/" className="text-[13px] text-accent hover:underline">
          ← Financial Report Intelligence
        </Link>
        <h1 className="mt-4 text-[34px] font-semibold tracking-[-0.03em]">Limitations</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-2">
          A research aid for reading UK annual reports, not investment advice. It is built to say
          when it cannot do something rather than guess. These are the things it does not do.
        </p>

        <Section title="Figures">
          <li>Only the primary statements are read: the income statement and the balance sheet. Notes, segment tables and the cash flow statement are not extracted.</li>
          <li>A figure is shown only when it is found in the PDF’s own text layer and passes its checks. Otherwise it is left empty with the reason; it is never estimated.</li>
          <li>Scanned PDFs without a text layer give suggestions for review only.</li>
          <li>Where no unit is printed, nothing is shown until a person confirms it.</li>
          <li>Tested on a small number of hand-labelled reports. Results on those are case studies, not an accuracy rate for annual reports in general.</li>
        </Section>

        <Section title="Ratios">
          <li>Ratios use fixed definitions and year-end balances, not averages. A seasonal business may look different within the year.</li>
          <li>For banks the four corporate ratios do not apply and are marked so. Two bank ratios are computed; a bank’s own capital and margin figures are quoted as reported, never recomputed.</li>
          <li>NHS trusts and insurers are not supported: their ratios are withheld until a person sets the document type.</li>
          <li>One report, two periods. No multi-year history, no peer comparison, no market data or valuation.</li>
        </Section>

        <Section title="Commentary">
          <li>Commentary is written from passages retrieved from the report, and every sentence must cite a quote that code has found in the report. It can still summarise a passage less well than a person would.</li>
          <li>Numbers in the commentary are inserted from the extracted figures or copied inside a verified quote; the model never writes a number.</li>
          <li>Where the report does not say enough, the topic says so instead of filling the gap.</li>
          <li>Generated text is not financial, legal or tax advice, and does not recommend buying, selling or holding anything.</li>
        </Section>

        <Section title="Operation">
          <li>Runs locally for one person. There are no accounts, sharing or access controls.</li>
          <li>The optional second table engine and the commentary model are external services; without their keys the tool runs on local engines and writes extractive commentary.</li>
        </Section>
      </main>
      <SiteFooter />
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6 rounded-2xl border border-line bg-surface p-6 shadow-[var(--shadow-card)]">
      <h2 className="text-[16px] font-semibold tracking-[-0.015em] text-ink">{title}</h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-[14px] leading-relaxed text-ink-2 marker:text-ink-3">{children}</ul>
    </section>
  );
}

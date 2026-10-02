"use client";

import { FileUp, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { ApiError, uploadPdf } from "@/lib/api";
import { cn } from "@/lib/cn";

const LIMIT = 50 * 1024 * 1024; // ingest.MAX_UPLOAD_BYTES; the API refuses anything larger too

const REFUSALS: Record<string, string> = {
  not_a_pdf: "That file isn’t a PDF.",
  file_too_large: "That file is over the 50 MB limit.",
  encrypted_pdf: "That PDF is password-protected, so it can’t be read.",
  unreadable_pdf: "That PDF couldn’t be opened. It may be damaged.",
};

/** The empty state (UI.md section 3): drop a PDF, then follow it through the stages. */
export function UploadDropzone() {
  const router = useRouter();
  const input = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const send = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
      setError(REFUSALS.not_a_pdf!);
      return;
    }
    if (file.size > LIMIT) {
      setError(REFUSALS.file_too_large!);
      return;
    }
    setBusy(file.name);
    try {
      const result = await uploadPdf(file);
      router.push(`/reports/${result.id}`);
    } catch (err) {
      setBusy(null);
      setError(err instanceof ApiError ? (REFUSALS[err.code] ?? err.message) : String(err));
    }
  };

  return (
    <div className="space-y-2">
      <div
        data-testid="upload-dropzone"
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          void send(e.dataTransfer.files[0]);
        }}
        className={cn(
          "flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          over ? "border-accent bg-accent-soft" : "border-line-strong bg-surface",
        )}
      >
        {busy ? (
          <>
            <Loader2 aria-hidden className="size-6 animate-spin text-accent motion-reduce:animate-none" />
            <p className="text-[14px] font-medium text-ink" aria-live="polite">
              Uploading {busy}…
            </p>
          </>
        ) : (
          <>
            <FileUp aria-hidden className="size-6 text-ink-3" />
            <p className="text-[14px] font-medium text-ink">
              Drop an annual report PDF (up to 50&nbsp;MB). Digitally born PDFs work best.
            </p>
            <button
              type="button"
              onClick={() => input.current?.click()}
              className="rounded-md border border-line-strong bg-surface px-3 py-1.5 text-[13px] font-medium text-ink hover:bg-surface-sunk"
            >
              Choose a file
            </button>
          </>
        )}
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          data-testid="upload-input"
          aria-label="Annual report PDF"
          onChange={(e) => void send(e.target.files?.[0])}
        />
      </div>
      {error ? (
        <p role="alert" data-testid="upload-error" className="text-[13px] text-missing">
          {error}
        </p>
      ) : null}
    </div>
  );
}

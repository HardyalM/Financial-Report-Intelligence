"use client";

import { FileUp, Loader2 } from "lucide-react";
import * as React from "react";
import { useUpload } from "@/components/shell/upload";
import { Kbd } from "@/components/pdf/toolbar";
import { shortcutLabel } from "@/components/pdf/use-viewer-input";
import { cn } from "@/lib/cn";

/** The empty state (UI.md section 3): drop a PDF, then follow it through the stages. */
export function UploadDropzone({ compact = false }: { compact?: boolean }) {
  const { send, busy, error } = useUpload();
  const input = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);

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
          "flex flex-col items-center rounded-2xl border border-dashed text-center transition-[background-color,border-color,transform] duration-200",
          compact ? "gap-2 px-5 py-6" : "gap-3 px-6 py-10",
          over ? "scale-[1.01] border-accent bg-accent-soft" : "border-line-strong bg-surface-sunk/60 hover:border-ink-3",
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
            <span className="flex size-11 items-center justify-center rounded-xl border border-line bg-surface shadow-[var(--shadow-card)]">
              <FileUp aria-hidden className="size-5 text-accent" />
            </span>
            <p className="text-[14px] font-medium text-ink">
              Drop an annual report PDF (up to 50&nbsp;MB). Digitally born PDFs work best.
            </p>
            <button
              type="button"
              onClick={() => input.current?.click()}
              className="rounded-lg bg-ink px-3.5 py-2 text-[13px] font-medium text-ink-inverse shadow-[var(--shadow-card)] transition-opacity hover:opacity-90"
            >
              Choose a file
            </button>
            {!compact ? (
              <p className="text-[11.5px] text-ink-3">
                Or drop it anywhere in the app · <Kbd>{shortcutLabel("mod+k")}</Kbd> for everything else
              </p>
            ) : null}
          </>
        )}
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          data-testid="upload-input"
          aria-label="Annual report PDF"
          onChange={(e) => {
            void send(e.target.files?.[0]);
            e.target.value = "";
          }}
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

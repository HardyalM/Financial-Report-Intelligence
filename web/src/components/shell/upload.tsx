"use client";

import { FileUp } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useToast } from "@/components/ui/toast";
import { ApiError, uploadPdf } from "@/lib/api";
import { spring } from "@/lib/motion";
import { useAddUploaded } from "@/lib/queries";

export const UPLOAD_LIMIT = 50 * 1024 * 1024; // ingest.MAX_UPLOAD_BYTES; the API refuses anything larger too

export const REFUSALS: Record<string, string> = {
  not_a_pdf: "That file isn’t a PDF.",
  file_too_large: "That file is over the 50 MB limit.",
  encrypted_pdf: "That PDF is password-protected, so it can’t be read.",
  unreadable_pdf: "That PDF couldn’t be opened. It may be damaged.",
};

interface UploadApi {
  /** Open the file picker. */
  pick: () => void;
  /** Send a file: checked here first, then uploaded; on success the report opens. */
  send: (file: File | undefined) => Promise<void>;
  busy: string | null;
  error: string | null;
}

const UploadContext = React.createContext<UploadApi | null>(null);

/**
 * One upload path for the whole app: the dashboard's drop zone, the sidebar and the command
 * palette all use it, and a PDF dropped anywhere on the window is caught here.
 */
export function UploadProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const toast = useToast();
  const addUploaded = useAddUploaded();
  const input = React.useRef<HTMLInputElement>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [dragging, setDragging] = React.useState(false);

  const send = React.useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      setError(null);
      const refuse = (message: string) => {
        setError(message);
        toast({ tone: "error", title: "Not uploaded", body: message });
      };
      if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") return refuse(REFUSALS.not_a_pdf!);
      if (file.size > UPLOAD_LIMIT) return refuse(REFUSALS.file_too_large!);
      setBusy(file.name);
      try {
        const result = await uploadPdf(file);
        addUploaded({ id: result.id, filename: file.name, status: result.status, page_count: 0 });
        if (result.duplicate) toast({ tone: "info", title: "Already read", body: `${file.name} was read before; opening that report.` });
        router.push(`/reports/${result.id}`);
      } catch (err) {
        refuse(err instanceof ApiError ? (REFUSALS[err.code] ?? err.message) : String(err));
      } finally {
        setBusy(null);
      }
    },
    [addUploaded, router, toast],
  );

  const pick = React.useCallback(() => input.current?.click(), []);

  // A PDF dragged over the window: one large, calm target instead of the browser opening it.
  React.useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => [...(e.dataTransfer?.types ?? [])].includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth++;
      setDragging(true);
    };
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const over = (e: DragEvent) => hasFiles(e) && e.preventDefault();
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      // A drop zone on the page handles its own drop; anything else lands here.
      if ((e.target as HTMLElement | null)?.closest("[data-testid=upload-dropzone]")) return;
      void send(e.dataTransfer?.files[0]);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [send]);

  const value = React.useMemo(() => ({ pick, send, busy, error }), [pick, send, busy, error]);
  return (
    <UploadContext.Provider value={value}>
      {children}
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          void send(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <AnimatePresence>
        {dragging ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="pointer-events-none fixed inset-0 z-[90] flex items-center justify-center bg-bg/70 backdrop-blur-sm"
          >
            <motion.div
              initial={{ scale: 0.96, y: 8 }}
              animate={{ scale: 1, y: 0 }}
              transition={spring.modal}
              className="flex flex-col items-center gap-3 rounded-3xl border-2 border-dashed border-accent bg-surface px-14 py-12 text-center shadow-[var(--shadow-pop)]"
            >
              <FileUp aria-hidden className="size-7 text-accent" />
              <p className="text-[16px] font-semibold tracking-[-0.01em] text-ink">Drop to analyse this report</p>
              <p className="text-[13px] text-ink-3">PDF up to 50 MB · digitally born works best</p>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </UploadContext.Provider>
  );
}

export function useUpload(): UploadApi {
  const value = React.useContext(UploadContext);
  if (!value) throw new Error("useUpload outside UploadProvider");
  return value;
}

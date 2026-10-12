"use client";

import { ChevronLeft, ChevronRight, FileWarning, Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { AnimatePresence } from "motion/react";
import * as React from "react";
import { PageView } from "@/components/pdf/page-view";
import { PdfReader } from "@/components/pdf/reader";
import { CloseButton } from "@/components/ui/close-button";
import { GlassToolbar, ToolButton, ToolDivider } from "@/components/pdf/toolbar";
import { useDragPan, useHotkeys, useIdle, usePinchZoom } from "@/components/pdf/use-viewer-input";
import { loadDocument, type PageBox } from "@/lib/pdf";
import { renderMode } from "@/lib/pdf-renderer";
import { usePageTheme } from "@/lib/pdf-theme";

export interface Highlight extends PageBox {
  page: number;
}

/** Zoom stops for the buttons and keys; a pinch can land anywhere between 50% and 400%. */
const ZOOMS = [1, 1.5, 2, 3];

/**
 * The original PDF in the evidence panel, one page at a time, with the cited text or the figure's
 * cell highlighted (UI.md 6.1). `page` and `highlights` come from code (citation.bbox,
 * value.bbox), never a model. Pages are drawn off the main thread; "Open document" opens the
 * whole PDF in the reader, at this page, with the same highlights.
 */
export function PdfViewer({
  url,
  page,
  highlights,
  folio,
  onPageChange,
  title = "Original report",
  onClose,
}: {
  url: string;
  page: number;
  highlights: Highlight[];
  folio: (page: number) => string | null;
  /** Told whenever the page on screen changes (the unit dialog uses it as the evidence page). */
  onPageChange?: (page: number) => void;
  title?: string;
  /** Close the source (the evidence panel's selection); shown as an × beside "Open document". */
  onClose?: () => void;
}) {
  const [doc, setDoc] = React.useState<PDFDocumentProxy | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [current, setCurrent] = React.useState(page);
  const [zoom, setZoom] = React.useState(1);
  const [size, setSize] = React.useState<{ width: number; height: number } | null>(null);
  const [rendered, setRendered] = React.useState<{ page: number; zoom: number } | null>(null);
  const [reader, setReader] = React.useState<{ query: string; search: boolean } | null>(null);
  const [hot, setHot] = React.useState(false);
  const frame = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);
  const theme = usePageTheme();
  const [idle, poke] = useIdle(2600);

  // A new selection (a different page or different boxes) brings the viewer to its page. Compared
  // by content: a background refresh rebuilds the same highlights, and must not undo the pages a
  // person turned since.
  const selectionKey = `${page}|${JSON.stringify(highlights)}`;
  React.useEffect(() => setCurrent(page), [selectionKey]); // eslint-disable-line react-hooks/exhaustive-deps
  React.useEffect(() => onPageChange?.(current), [current, onPageChange]);

  React.useEffect(() => {
    let live = true;
    setError(null);
    loadDocument(url).then(
      (d) => live && setDoc(d),
      () => live && setError("The original PDF isn’t available, so the page can’t be shown."),
    );
    return () => {
      live = false;
    };
  }, [url]);

  React.useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry!.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    if (!doc) return;
    if (current < 1 || current > doc.numPages) {
      setError(`Page ${current} is outside this PDF (1–${doc.numPages}).`);
      return;
    }
    setError(null);
    let live = true;
    doc.getPage(current).then((p) => {
      if (!live) return;
      const v = p.getViewport({ scale: 1 });
      setSize({ width: v.width, height: v.height });
    });
    return () => {
      live = false;
    };
  }, [doc, current]);

  const fit = size && width ? width / size.width : 0;
  const scale = fit * zoom;
  const onPage = React.useMemo(() => highlights.filter((h) => h.page === current), [highlights, current]);

  const onRendered = React.useCallback(
    (p: number, s: number) => setRendered({ page: p, zoom: fit ? s / fit : 1 }),
    [fit],
  );
  // No reset when the page changes: a cached page reports itself drawn from its own (child)
  // effect, which runs before an effect here would, so a reset would erase it. `rendered.page`
  // is compared with `current` wherever it is read instead.

  // Bring the first highlight into view inside the panel once the page is drawn.
  React.useEffect(() => {
    if (rendered === null) return;
    frame.current?.querySelector<HTMLElement>("[data-testid=highlight-box]")?.scrollIntoView({ block: "center", inline: "nearest" });
  }, [rendered?.page, onPage]); // eslint-disable-line react-hooks/exhaustive-deps

  // The hook keeps zoom inside its limits (and rubber-bands a pinch past them).
  const zoomAt = usePinchZoom(frame, zoom, setZoom);
  const panning = useDragPan(frame);
  /** Zoom to a level, anchored at the middle of the page view so the place being read stays. */
  const zoomTo = (target: number) => {
    const el = frame.current;
    if (!el) return setZoom(target);
    const box = el.getBoundingClientRect();
    zoomAt(target, box.left + box.width / 2, box.top + box.height / 2);
    poke();
  };
  const step = (dir: 1 | -1) => {
    const stops = dir > 0 ? ZOOMS.filter((z) => z > zoom + 0.01) : ZOOMS.filter((z) => z < zoom - 0.01).reverse();
    const next = stops[0] ?? (dir > 0 ? ZOOMS.at(-1)! : ZOOMS[0]!);
    const el = frame.current;
    if (!el) return setZoom(next);
    const box = el.getBoundingClientRect();
    zoomAt(next, box.left + box.width / 2, box.top + box.height / 2);
    poke();
  };

  const total = doc?.numPages ?? null;
  const go = (n: number) => total && n >= 1 && n <= total && setCurrent(n);
  // Keys apply while the pointer is over the viewer or focus is inside it (never while reading).
  useHotkeys(hot && !reader, [
    { combo: "arrowleft", run: () => go(current - 1) },
    { combo: "arrowright", run: () => go(current + 1) },
    { combo: "mod+=", run: () => step(1) },
    { combo: "mod+-", run: () => step(-1) },
    { combo: "mod+0", run: () => zoomTo(1) },
    { combo: "mod+f", run: () => setReader({ query: "", search: true }) },
  ]);

  const printed = folio(current);
  const shownZoom = Math.round(zoom * 100);
  return (
    <div
      className="flex flex-col"
      data-testid="pdf-viewer"
      data-page={current}
      data-rendered-page={rendered?.page === current ? current : ""}
      data-rendered-zoom={rendered?.page === current ? Math.round(rendered.zoom * 100) : ""}
      data-render-mode={rendered ? renderMode() : ""}
      onPointerEnter={() => setHot(true)}
      onPointerLeave={(e) => setHot(e.currentTarget.contains(document.activeElement))}
      onFocus={() => setHot(true)}
      onBlur={(e) => !e.currentTarget.contains(e.relatedTarget as Node) && setHot(false)}
    >
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <span className="num min-w-0 truncate text-[0.75rem] text-ink-2" data-testid="viewer-page-label" aria-live="polite">
          PDF p.&nbsp;{current}
          {printed ? ` · printed p. ${printed}` : ""}
          {total ? <span className="text-ink-3"> / {total}</span> : null}
        </span>
        <div className="flex shrink-0 items-center gap-0.5">
        <button
          type="button"
          disabled={!doc}
          onClick={() => setReader({ query: "", search: false })}
          data-testid="open-reader"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-[0.75rem] font-medium text-ink-2 transition-colors hover:bg-surface-sunk hover:text-ink disabled:opacity-40"
        >
          <Maximize2 aria-hidden className="size-3.5" />
          Open document
        </button>
        {onClose ? <CloseButton onClose={onClose} /> : null}
        </div>
      </div>
      <div className="pdf-stage relative" onPointerMove={poke}>
        <div
          ref={frame}
          className={`relative max-h-[62vh] overflow-auto overscroll-contain bg-[var(--pdf-desk)] ${panning ? "cursor-grab active:cursor-grabbing" : ""}`}
        >
          {error ? (
            <div className="flex min-h-48 flex-col items-center justify-center gap-2 px-6 py-10 text-center" data-testid="viewer-error">
              <FileWarning aria-hidden className="size-5 text-ink-3" />
              <p className="text-[0.78125rem] text-ink-2">{error}</p>
            </div>
          ) : doc && size && scale ? (
            <div className="mx-auto w-fit min-w-full pb-16">
              <PageView
                key={current}
                url={url}
                doc={doc}
                page={current}
                scale={scale}
                size={size}
                theme={theme}
                highlights={onPage}
                onRendered={onRendered}
                className="mx-auto"
              />
            </div>
          ) : (
            <div aria-hidden className="pdf-skeleton mx-auto aspect-[1/1.414] w-full bg-[var(--pdf-paper)]" />
          )}
        </div>
        {!error ? (
          <GlassToolbar idle={idle} className="bottom-3">
            <ToolButton label="Previous page" shortcut="arrowleft" disabled={current <= 1} onClick={() => setCurrent((n) => n - 1)}>
              <ChevronLeft aria-hidden />
            </ToolButton>
            <ToolButton label="Next page" shortcut="arrowright" disabled={total !== null && current >= total} onClick={() => setCurrent((n) => n + 1)}>
              <ChevronRight aria-hidden />
            </ToolButton>
            <ToolDivider />
            <ToolButton label="Zoom out" shortcut="mod+-" disabled={zoom <= ZOOMS[0]! + 0.001} onClick={() => step(-1)}>
              <ZoomOut aria-hidden />
            </ToolButton>
            <span className="num w-11 text-center text-[0.71875rem] font-medium text-ink-2">{shownZoom}%</span>
            <ToolButton label="Zoom in" shortcut="mod+=" disabled={zoom >= ZOOMS.at(-1)! - 0.001} onClick={() => step(1)}>
              <ZoomIn aria-hidden />
            </ToolButton>
          </GlassToolbar>
        ) : null}
      </div>
      <AnimatePresence>
      {reader && doc ? (
        <PdfReader
          key="reader"
          url={url}
          doc={doc}
          title={title}
          initialPage={current}
          highlights={highlights}
          folio={folio}
          initialQuery={reader.query}
          focusSearch={reader.search}
          onClose={(p) => {
            setReader(null);
            setCurrent(p);
          }}
        />
      ) : null}
      </AnimatePresence>
    </div>
  );
}

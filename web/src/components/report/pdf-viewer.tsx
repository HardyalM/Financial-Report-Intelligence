"use client";

import { ChevronLeft, ChevronRight, FileWarning, Loader2, ZoomIn, ZoomOut } from "lucide-react";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { loadDocument, type PageBox, toViewport } from "@/lib/pdf";

export interface Highlight extends PageBox {
  page: number;
}

const ZOOMS = [1, 1.5, 2, 3];

/**
 * The original PDF, one page at a time, with the cited text or the figure's cell highlighted
 * (UI.md 6.1). `page` and `highlights` come from code (citation.bbox, value.bbox), never a model.
 */
export function PdfViewer({
  url,
  page,
  highlights,
  folio,
}: {
  url: string;
  page: number;
  highlights: Highlight[];
  folio: (page: number) => string | null;
}) {
  const [doc, setDoc] = React.useState<PDFDocumentProxy | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [current, setCurrent] = React.useState(page);
  const [zoom, setZoom] = React.useState(0);
  const [rendered, setRendered] = React.useState<{ page: number; zoom: number } | null>(null);
  const [boxes, setBoxes] = React.useState<{ left: number; top: number; width: number; height: number }[]>([]);
  const frame = React.useRef<HTMLDivElement>(null);
  const canvas = React.useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = React.useState(0);

  React.useEffect(() => setCurrent(page), [page, highlights]);

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
    if (!doc || !canvas.current || width === 0) return;
    if (current < 1 || current > doc.numPages) {
      setError(`Page ${current} is outside this PDF (1–${doc.numPages}).`);
      return;
    }
    let task: RenderTask | null = null;
    let live = true;
    setRendered(null);
    doc.getPage(current).then((p: PDFPageProxy) => {
      if (!live || !canvas.current) return;
      const base = p.getViewport({ scale: 1 });
      const scale = (width / base.width) * ZOOMS[zoom]!;
      const viewport = p.getViewport({ scale });
      const ratio = window.devicePixelRatio || 1;
      const c = canvas.current;
      c.width = Math.floor(viewport.width * ratio);
      c.height = Math.floor(viewport.height * ratio);
      c.style.width = `${Math.floor(viewport.width)}px`;
      c.style.height = `${Math.floor(viewport.height)}px`;
      task = p.render({
        canvas: c,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      task.promise.then(
        () => {
          if (!live) return;
          setBoxes(highlights.filter((h) => h.page === current).map((h) => toViewport(p, viewport, h)));
          setRendered({ page: current, zoom: ZOOMS[zoom]! });
        },
        () => undefined,
      );
    });
    return () => {
      live = false;
      task?.cancel();
    };
  }, [doc, current, width, zoom, highlights]);

  // Bring the first highlight into view inside the panel.
  React.useEffect(() => {
    if (rendered === null) return;
    frame.current?.querySelector<HTMLElement>("[data-testid=highlight-box]")?.scrollIntoView({ block: "center", inline: "nearest" });
  }, [rendered, boxes]);

  const total = doc?.numPages ?? null;
  const printed = folio(current);
  return (
    <div
      className="flex flex-col"
      data-testid="pdf-viewer"
      data-page={current}
      data-rendered-page={rendered?.page ?? ""}
      data-rendered-zoom={rendered ? Math.round(rendered.zoom * 100) : ""}
    >
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" aria-label="Previous page" disabled={current <= 1} onClick={() => setCurrent((n) => n - 1)}>
            <ChevronLeft aria-hidden />
          </Button>
          <span className="num min-w-0 text-[12px] text-ink-2" data-testid="viewer-page-label" aria-live="polite">
            PDF p.&nbsp;{current}
            {printed ? ` · printed p. ${printed}` : ""}
            {total ? <span className="text-ink-3"> / {total}</span> : null}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Next page"
            disabled={total !== null && current >= total}
            onClick={() => setCurrent((n) => n + 1)}
          >
            <ChevronRight aria-hidden />
          </Button>
        </div>
        <div className="flex items-center gap-0.5">
          <Tooltip content="Zoom out">
            <Button variant="ghost" size="icon" aria-label="Zoom out" disabled={zoom === 0} onClick={() => setZoom((z) => z - 1)}>
              <ZoomOut aria-hidden />
            </Button>
          </Tooltip>
          <span className="num w-10 text-center text-[11px] text-ink-3">{Math.round(ZOOMS[zoom]! * 100)}%</span>
          <Tooltip content="Zoom in">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Zoom in"
              disabled={zoom === ZOOMS.length - 1}
              onClick={() => setZoom((z) => z + 1)}
            >
              <ZoomIn aria-hidden />
            </Button>
          </Tooltip>
        </div>
      </div>
      <div ref={frame} className="relative max-h-[62vh] overflow-auto bg-surface-sunk p-0">
        {error ? (
          <div className="flex min-h-48 flex-col items-center justify-center gap-2 px-6 py-10 text-center" data-testid="viewer-error">
            <FileWarning aria-hidden className="size-5 text-ink-3" />
            <p className="text-[12.5px] text-ink-2">{error}</p>
          </div>
        ) : (
          <div className="relative mx-auto min-h-48 w-fit min-w-full">
            <canvas ref={canvas} className="block bg-white" aria-label={`PDF page ${current}`} role="img" />
            {rendered?.page === current
              ? boxes.map((b, i) => (
                  <div
                    key={i}
                    data-testid="highlight-box"
                    className="pdf-highlight pointer-events-none absolute"
                    style={{ left: b.left - 2, top: b.top - 2, width: b.width + 4, height: b.height + 4 }}
                  />
                ))
              : null}
            {rendered?.page !== current ? (
              <div className="absolute inset-0 flex min-h-48 items-center justify-center">
                <Loader2 aria-hidden className="size-5 animate-spin text-ink-3" />
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

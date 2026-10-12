"use client";

import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import * as React from "react";
import { cn } from "@/lib/cn";
import { type PageBox, pdfViewerLib, toViewport } from "@/lib/pdf";
import { peekAnyScale, peekRendered, type Rendered, renderPage } from "@/lib/pdf-renderer";
import type { PageTheme } from "@/lib/pdf-theme";

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** CSS pixels per PDF point at zoom 1 are the caller's; this is what the page needs to know. */
export interface PageViewProps {
  url: string;
  doc: PDFDocumentProxy;
  page: number;
  /** CSS pixels per PDF point. */
  scale: number;
  /** The page's size in PDF points (rotation applied), for layout before it is drawn. */
  size: { width: number; height: number };
  theme: PageTheme | null;
  highlights?: PageBox[];
  /** A search query: matches in this page's text are marked. */
  query?: string;
  /** Index of the match (on this page) that is the current one, or -1. */
  activeMatch?: number;
  /** Selectable text. Off for thumbnails. */
  textLayer?: boolean;
  /** Re-render at a new scale only after the scale has been still this long (pinch, zoom keys). */
  settleMs?: number;
  className?: string;
  onRendered?: (page: number, scale: number) => void;
  onMatches?: (page: number, count: number) => void;
  label?: string;
}

/**
 * One page: an instant first frame (cached bitmap, or a lower-resolution one stretched), a
 * skeleton while nothing is ready, a fade-in when the sharp render lands, pdf.js's own text layer
 * for native selection, and highlight boxes from code (citation.bbox, value.bbox).
 */
export function PageView({
  url,
  doc,
  page,
  scale,
  size,
  theme,
  highlights = [],
  query = "",
  activeMatch = -1,
  textLayer = true,
  settleMs = 140,
  className,
  onRendered,
  onMatches,
  label,
}: PageViewProps) {
  const canvas = React.useRef<HTMLCanvasElement>(null);
  const textHost = React.useRef<HTMLDivElement>(null);
  const [proxy, setProxy] = React.useState<PDFPageProxy | null>(null);
  const [drawn, setDrawn] = React.useState<{ scale: number; sharp: boolean } | null>(null);
  const [renderScale, setRenderScale] = React.useState(scale);
  const [textReady, setTextReady] = React.useState(0);
  const [marks, setMarks] = React.useState<Rect[]>([]);
  const width = Math.floor(size.width * scale);
  const height = Math.floor(size.height * scale);
  const dpr = typeof window === "undefined" ? 1 : Math.min(window.devicePixelRatio || 1, 3);

  React.useEffect(() => {
    let live = true;
    doc.getPage(page).then((p) => live && setProxy(p), () => undefined);
    return () => {
      live = false;
    };
  }, [doc, page]);

  // A scale that is still moving (pinch, held zoom key) is shown stretched; the render waits.
  React.useEffect(() => {
    if (scale === renderScale) return;
    const t = window.setTimeout(() => setRenderScale(scale), drawn ? settleMs : 0);
    return () => window.clearTimeout(t);
  }, [scale, renderScale, settleMs, drawn]);

  const paint = React.useCallback((r: Rendered) => {
    const c = canvas.current;
    if (!c) return;
    c.width = r.width;
    c.height = r.height;
    c.getContext("2d")?.drawImage(r.bitmap, 0, 0);
  }, []);

  React.useEffect(() => {
    const request = { url, page, scale: renderScale * dpr, theme };
    const exact = peekRendered(request);
    if (exact) {
      paint(exact);
      setDrawn({ scale: renderScale, sharp: true });
      onRendered?.(page, renderScale);
      return;
    }
    const rough = peekAnyScale(url, page, theme);
    if (rough) {
      paint(rough);
      setDrawn((d) => ({ scale: d?.scale ?? renderScale, sharp: false }));
    }
    const abort = new AbortController();
    renderPage(request, abort.signal).then(
      (r) => {
        if (abort.signal.aborted) return;
        paint(r);
        setDrawn({ scale: renderScale, sharp: true });
        onRendered?.(page, renderScale);
      },
      () => undefined,
    );
    return () => abort.abort();
    // onRendered is a notification; a new function identity must not re-render the page
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, page, renderScale, dpr, theme, paint]);

  // pdf.js's text layer: real DOM text, positioned over the glyphs, so selection is native.
  // Loaded after the page's first image is on screen: the text layer must never delay it.
  const painted = drawn !== null;
  React.useEffect(() => {
    const host = textHost.current;
    if (!textLayer || !proxy || !host || !painted) return;
    let live = true;
    let builder: { div: HTMLDivElement; cancel: () => void } | null = null;
    pdfViewerLib().then(async ({ TextLayerBuilder }) => {
      if (!live) return;
      const b = new TextLayerBuilder({ pdfPage: proxy });
      builder = b;
      try {
      // No image layer: pictures stay on the canvas; only text is selectable.
      await b.render({ viewport: proxy.getViewport({ scale: 1 }) } as Parameters<typeof b.render>[0]);
        if (!live) return;
        host.replaceChildren(b.div);
        setTextReady((n) => n + 1);
      } catch {
        // cancelled because the page scrolled away or the scale changed: nothing to show
      }
    }, () => undefined);
    return () => {
      live = false;
      builder?.cancel();
      host.replaceChildren();
    };
  }, [proxy, textLayer, painted]);

  const boxes = React.useMemo(() => {
    if (!proxy) return [];
    const viewport = proxy.getViewport({ scale });
    return highlights.map((h) => toViewport(proxy, viewport, h));
  }, [proxy, scale, highlights]);

  // Search marks: measured from the text layer's own text nodes, so they sit on the glyphs.
  React.useLayoutEffect(() => {
    const host = textHost.current;
    const needle = query.trim().toLocaleLowerCase();
    if (!host || !needle || !textReady) {
      setMarks([]);
      onMatches?.(page, 0);
      return;
    }
    const origin = host.getBoundingClientRect();
    const found: Rect[] = [];
    const spans = host.querySelectorAll<HTMLElement>(".textLayer span:not(.markedContent)");
    for (const span of spans) {
      const node = span.firstChild;
      if (!node || node.nodeType !== Node.TEXT_NODE) continue;
      const text = (node.textContent ?? "").toLocaleLowerCase();
      for (let at = text.indexOf(needle); at >= 0; at = text.indexOf(needle, at + needle.length)) {
        const range = document.createRange();
        range.setStart(node, at);
        range.setEnd(node, at + needle.length);
        const r = range.getBoundingClientRect();
        if (r.width && r.height) {
          found.push({ left: r.left - origin.left, top: r.top - origin.top, width: r.width, height: r.height });
        }
      }
    }
    setMarks(found);
    onMatches?.(page, found.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, textReady, scale, page]);

  const ready = drawn !== null;
  return (
    <div
      className={cn("pdf-page relative overflow-hidden bg-[var(--pdf-paper)] shadow-[var(--shadow-raised)]", className)}
      style={
        {
          width,
          height,
          "--total-scale-factor": scale,
          "--scale-round-x": "1px",
          "--scale-round-y": "1px",
        } as React.CSSProperties
      }
      data-page-number={page}
      data-rendered={drawn?.sharp ? "true" : "false"}
    >
      {!ready ? <div aria-hidden className="pdf-skeleton absolute inset-0" /> : null}
      <canvas
        ref={canvas}
        role="img"
        aria-label={label ?? `PDF page ${page}`}
        className={cn(
          "absolute inset-0 block size-full transition-opacity duration-300 ease-out motion-reduce:transition-none",
          ready ? "opacity-100" : "opacity-0",
          drawn && !drawn.sharp && "blur-[0.4px]",
        )}
      />
      {textLayer ? <div ref={textHost} className="pdf-text-host absolute inset-0" /> : null}
      {marks.map((m, i) => (
        <div
          key={`m${i}`}
          data-testid="search-hit"
          data-active={i === activeMatch ? "true" : undefined}
          className={cn("pdf-search-hit pointer-events-none absolute", i === activeMatch && "pdf-search-hit-active")}
          style={{ left: m.left - 1, top: m.top - 1, width: m.width + 2, height: m.height + 2 }}
        />
      ))}
      {boxes.map((b, i) => (
        <div
          key={`h${i}`}
          data-testid="highlight-box"
          className="pdf-highlight pointer-events-none absolute"
          style={{ left: b.left - 2, top: b.top - 2, width: b.width + 4, height: b.height + 4 }}
        />
      ))}
    </div>
  );
}

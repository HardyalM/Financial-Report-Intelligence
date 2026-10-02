"use client";

/**
 * pdf.js access. One document per report, loaded on first use and shared by every view of it.
 * Coordinates: figure boxes are unrotated PDF points with the origin top-left (text layer, SCHEMA
 * 4.1); citation boxes are display-space points, top-left (narrative chunks, RAG 5).
 */
import type { PDFDocumentProxy, PDFPageProxy, PageViewport } from "pdfjs-dist";

type PdfJs = typeof import("pdfjs-dist");
let lib: Promise<PdfJs> | null = null;
const docs = new Map<string, Promise<PDFDocumentProxy>>();

function pdfjs(): Promise<PdfJs> {
  lib ??= import("pdfjs-dist").then((m) => {
    m.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
    return m;
  });
  return lib;
}

export function loadDocument(url: string): Promise<PDFDocumentProxy> {
  let doc = docs.get(url);
  if (!doc) {
    doc = pdfjs().then((m) => m.getDocument({ url }).promise);
    doc.catch(() => docs.delete(url));
    docs.set(url, doc);
  }
  return doc;
}

export type BoxSpace = "unrotated" | "display";

export interface PageBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  space: BoxSpace;
}

/** A box on the page in viewport (CSS pixel) coordinates: left, top, width, height. */
export function toViewport(
  page: PDFPageProxy,
  viewport: PageViewport,
  box: PageBox,
): { left: number; top: number; width: number; height: number } {
  let a: number[];
  let b: number[];
  if (box.space === "display") {
    a = [box.x0 * viewport.scale, box.y0 * viewport.scale];
    b = [box.x1 * viewport.scale, box.y1 * viewport.scale];
  } else {
    const [vx0, , , vy1] = page.view as [number, number, number, number];
    a = viewport.convertToViewportPoint(vx0 + box.x0, vy1 - box.y0) as number[];
    b = viewport.convertToViewportPoint(vx0 + box.x1, vy1 - box.y1) as number[];
  }
  const left = Math.min(a[0]!, b[0]!);
  const top = Math.min(a[1]!, b[1]!);
  return { left, top, width: Math.abs(b[0]! - a[0]!), height: Math.abs(b[1]! - a[1]!) };
}

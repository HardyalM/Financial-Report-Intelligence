/// <reference lib="webworker" />
/**
 * The PDF render worker. pdf.js parses in its own worker as always; this worker also rasterises,
 * on an OffscreenCanvas, so the page you scroll never waits for a page being drawn. Each finished
 * page goes back as an ImageBitmap (transferred, not copied).
 *
 * Dark pages: lightness is inverted with the hue kept, then mapped onto the app's own surface and
 * ink colours. Image areas (recorded by pdf.js while drawing) are left exactly as printed.
 */
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

type Rgb = [number, number, number];

export type ToWorker =
  | { type: "open"; doc: string; url: string }
  | { type: "render"; id: number; doc: string; page: number; scale: number; theme: { bg: Rgb; fg: Rgb } | null }
  | { type: "cancel"; id: number };

export type FromWorker =
  | { type: "opened"; doc: string; pages: number }
  | { type: "failed"; doc: string; message: string }
  | { type: "rendered"; id: number; bitmap: ImageBitmap }
  | { type: "render-failed"; id: number; message: string; cancelled: boolean }
  | { type: "log"; message: string };

const scope = self as unknown as DedicatedWorkerGlobalScope;
scope.addEventListener("unhandledrejection", (e) => post({ type: "log", message: `unhandled: ${String(e.reason)}` }));
scope.addEventListener("error", (e) => post({ type: "log", message: `error: ${e.message}` }));

/** Canvases for pdf.js's own intermediate drawing (patterns, masks): offscreen too. */
class OffscreenCanvasFactory {
  create(width: number, height: number) {
    if (width <= 0 || height <= 0) throw new Error("Invalid canvas size");
    const canvas = new OffscreenCanvas(width, height);
    return { canvas, context: canvas.getContext("2d", { willReadFrequently: true }) };
  }
  reset(cc: { canvas: OffscreenCanvas | null }, width: number, height: number) {
    if (!cc.canvas) throw new Error("Canvas is not specified");
    cc.canvas.width = width;
    cc.canvas.height = height;
  }
  destroy(cc: { canvas: OffscreenCanvas | null; context: unknown }) {
    if (cc.canvas) cc.canvas.width = cc.canvas.height = 0;
    cc.canvas = null;
    cc.context = null;
  }
}

/** SVG filters need a DOM; here none is available, so every filter is the identity. */
class NoFilterFactory {
  addFilter() {
    return "none";
  }
  addHCMFilter() {
    return "none";
  }
  addAlphaFilter() {
    return "none";
  }
  addLuminosityFilter() {
    return "none";
  }
  addKnockoutFilter() {
    return "none";
  }
  addHighlightHCMFilter() {
    return "none";
  }
  addSelectionHCMFilter() {
    return "none";
  }
  addSelectionFilter() {
    return "none";
  }
  createSelectionStyle() {
    return "";
  }
  destroy() {}
}

// There is no `window` here, and pdf.js would normally start its own parsing worker from this
// one; nested workers are not available everywhere (they fail in some Chromium shells), so pdf.js
// parses in this thread instead ("fake worker" mode, enabled by `globalThis.pdfjsWorker`). Both
// parsing and drawing stay off the main thread. The document URL is passed as a URL object, so
// pdf.js never resolves it against `window.location`.
const pdfjs = Promise.all([import("pdfjs-dist"), import("pdfjs-dist/build/pdf.worker.min.mjs")]).then(
  ([m, parser]) => {
    (globalThis as unknown as { pdfjsWorker: unknown }).pdfjsWorker = parser;
    return m;
  },
);
const docs = new Map<string, Promise<PDFDocumentProxy>>();

interface Job {
  id: number;
  doc: string;
  page: number;
  scale: number;
  theme: { bg: Rgb; fg: Rgb } | null;
}
const queue: Job[] = [];
const running = new Map<number, RenderTask | null>();
const cancelled = new Set<number>();
const PARALLEL = 2;

scope.onmessage = (event: MessageEvent<ToWorker>) => {
  const msg = event.data;
  if (msg.type === "open") {
    if (!docs.has(msg.doc)) {
      const doc = pdfjs.then((m) =>
        m.getDocument({
          url: new URL(msg.url),
          CanvasFactory: OffscreenCanvasFactory,
          FilterFactory: NoFilterFactory,
          disableFontFace: true, // glyphs drawn as paths: FontFace needs a document
          isOffscreenCanvasSupported: true,
          verbosity: m.VerbosityLevel.ERRORS, // not "Setting up fake worker": that is intended here
        } as Parameters<typeof m.getDocument>[0]).promise,
      );
      docs.set(msg.doc, doc);
      doc.then(
        (d) => post({ type: "opened", doc: msg.doc, pages: d.numPages }),
        (e: unknown) => {
          docs.delete(msg.doc);
          post({ type: "failed", doc: msg.doc, message: String(e) });
        },
      );
    }
    return;
  }
  if (msg.type === "cancel") {
    const at = queue.findIndex((j) => j.id === msg.id);
    if (at >= 0) {
      queue.splice(at, 1);
      post({ type: "render-failed", id: msg.id, message: "cancelled", cancelled: true });
    } else if (running.has(msg.id)) {
      cancelled.add(msg.id);
      running.get(msg.id)?.cancel();
    }
    return;
  }
  queue.push(msg);
  pump();
};

function post(msg: FromWorker, transfer: Transferable[] = []) {
  scope.postMessage(msg, transfer);
}

/** Newest request first: the page you just scrolled to matters more than one you passed. */
function pump() {
  while (running.size < PARALLEL && queue.length) {
    const job = queue.pop()!;
    running.set(job.id, null);
    void render(job).finally(() => {
      running.delete(job.id);
      cancelled.delete(job.id);
      pump();
    });
  }
}

async function render(job: Job) {
  try {
    const doc = await docs.get(job.doc);
    if (!doc) throw new Error("document not open");
    const page = await doc.getPage(job.page);
    if (cancelled.has(job.id)) throw new Error("cancelled");
    const viewport = page.getViewport({ scale: job.scale });
    const canvas = new OffscreenCanvas(Math.max(1, Math.floor(viewport.width)), Math.max(1, Math.floor(viewport.height)));
    const task = page.render({
      canvas: canvas as unknown as HTMLCanvasElement,
      viewport,
      recordImages: job.theme !== null,
    });
    running.set(job.id, task);
    await task.promise;
    if (job.theme) recolour(canvas, job.theme, page.imageCoordinates as ArrayLike<number> | null);
    const bitmap = canvas.transferToImageBitmap();
    post({ type: "rendered", id: job.id, bitmap }, [bitmap]);
  } catch (e) {
    const wasCancelled = cancelled.has(job.id) || String(e).includes("cancel");
    const message = e instanceof Error && e.stack ? `${e.message}\n${e.stack}` : String(e);
    post({ type: "render-failed", id: job.id, message, cancelled: wasCancelled });
  }
}

/**
 * Dark page: for each pixel, lightness is inverted with the hue kept (adding 255 − max − min to
 * every channel), then 0..255 is mapped onto bg..fg. Pixels inside recorded images are untouched.
 */
function recolour(canvas: OffscreenCanvas, theme: { bg: Rgb; fg: Rgb }, images: ArrayLike<number> | null) {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return;
  const { width, height } = canvas;
  const keep = imageRects(images, width, height);
  const saved = keep.map((r) => ({ r, data: ctx.getImageData(r.x, r.y, r.w, r.h) }));
  const img = ctx.getImageData(0, 0, width, height);
  const d = img.data;
  const [br, bg, bb] = theme.bg;
  const dr = (theme.fg[0] - br) / 255;
  const dg = (theme.fg[1] - bg) / 255;
  const db = (theme.fg[2] - bb) / 255;
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i]!;
    const g = d[i + 1]!;
    const b = d[i + 2]!;
    const shift = 255 - Math.max(r, g, b) - Math.min(r, g, b);
    d[i] = br + (r + shift) * dr;
    d[i + 1] = bg + (g + shift) * dg;
    d[i + 2] = bb + (b + shift) * db;
  }
  ctx.putImageData(img, 0, 0);
  for (const { r, data } of saved) ctx.putImageData(data, r.x, r.y);
}

/** pdf.js records each image as three normalised corners of a parallelogram. */
function imageRects(coords: ArrayLike<number> | null, width: number, height: number) {
  const rects: { x: number; y: number; w: number; h: number }[] = [];
  if (!coords) return rects;
  for (let i = 0; i + 5 < coords.length; i += 6) {
    const xs = [coords[i]!, coords[i + 2]!, coords[i + 4]!, coords[i + 2]! + coords[i + 4]! - coords[i]!];
    const ys = [coords[i + 1]!, coords[i + 3]!, coords[i + 5]!, coords[i + 3]! + coords[i + 5]! - coords[i + 1]!];
    const x = Math.max(0, Math.floor(Math.min(...xs) * width));
    const y = Math.max(0, Math.floor(Math.min(...ys) * height));
    const x1 = Math.min(width, Math.ceil(Math.max(...xs) * width));
    const y1 = Math.min(height, Math.ceil(Math.max(...ys) * height));
    // A full-page image is a scan or a background, not a picture on a page: recolour it.
    if (x1 - x > 0 && y1 - y > 0 && (x1 - x) * (y1 - y) < 0.85 * width * height) {
      rects.push({ x, y, w: x1 - x, h: y1 - y });
    }
  }
  return rects;
}

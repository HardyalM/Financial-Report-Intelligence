"use client";

/**
 * Page rendering off the main thread. One render worker (pdf-render.worker.ts) for the app; a
 * bitmap cache so a page you return to appears at once; cancellation, so pages scrolled past are
 * never drawn. If the worker can't start (no OffscreenCanvas), pages render on the main thread
 * with pdf.js as before, and nothing else changes.
 */
import type { FromWorker, ToWorker } from "@/lib/pdf-render.worker";
import { loadDocument } from "@/lib/pdf";
import type { PageTheme } from "@/lib/pdf-theme";

export interface RenderRequest {
  url: string;
  page: number;
  /** Device pixels per PDF point (CSS scale × devicePixelRatio). */
  scale: number;
  theme: PageTheme | null;
}

export interface Rendered {
  bitmap: ImageBitmap | HTMLCanvasElement;
  width: number;
  height: number;
}

const CACHE_LIMIT_PIXELS = 160 * 1_000_000; // ~640 MB of RGBA at most, usually far less
const cache = new Map<string, Rendered>(); // insertion order = recency
let cachedPixels = 0;

let worker: Worker | null | undefined;
const OPEN_TIMEOUT_MS = 8000;
let nextId = 1;
const pending = new Map<number, { resolve: (r: Rendered) => void; reject: (e: Error) => void }>();
const opened = new Map<string, Promise<number>>();
const ready = new Set<string>(); // documents the worker has finished opening
const openWaiters = new Map<string, { resolve: (n: number) => void; reject: (e: Error) => void }>();

function key(r: RenderRequest): string {
  const t = r.theme ? `${r.theme.bg.join(",")}/${r.theme.fg.join(",")}` : "light";
  return `${r.url}#${r.page}@${r.scale.toFixed(3)}:${t}`;
}

function remember(k: string, value: Rendered) {
  cache.delete(k);
  cache.set(k, value);
  cachedPixels += value.width * value.height;
  for (const [old, v] of cache) {
    if (cachedPixels <= CACHE_LIMIT_PIXELS) break;
    if (old === k) continue;
    cache.delete(old);
    cachedPixels -= v.width * v.height;
    if ("close" in v.bitmap) v.bitmap.close();
  }
}

/** A rendered page already in memory, without asking for it (for an instant first frame). */
export function peekRendered(r: RenderRequest): Rendered | null {
  const hit = cache.get(key(r));
  if (hit) {
    cache.delete(key(r));
    cache.set(key(r), hit);
  }
  return hit ?? null;
}

/** The best cached render of this page at any scale: shown stretched while the sharp one draws. */
export function peekAnyScale(url: string, page: number, theme: PageTheme | null): Rendered | null {
  const prefix = `${url}#${page}@`;
  const t = theme ? `${theme.bg.join(",")}/${theme.fg.join(",")}` : "light";
  let best: Rendered | null = null;
  for (const [k, v] of cache) {
    if (k.startsWith(prefix) && k.endsWith(`:${t}`) && (!best || v.width > best.width)) best = v;
  }
  return best;
}

function getWorker(): Worker | null {
  if (worker !== undefined) return worker;
  try {
    if (typeof OffscreenCanvas === "undefined" || typeof createImageBitmap === "undefined") throw new Error("no offscreen");
    worker = new Worker(new URL("./pdf-render.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<FromWorker>) => {
      const msg = event.data;
      if (msg.type === "log") console.warn(`pdf worker: ${msg.message}`);
      else if (msg.type === "opened") openWaiters.get(msg.doc)?.resolve(msg.pages);
      else if (msg.type === "failed") openWaiters.get(msg.doc)?.reject(new Error(msg.message));
      else if (msg.type === "rendered") {
        const p = pending.get(msg.id);
        pending.delete(msg.id);
        p?.resolve({ bitmap: msg.bitmap, width: msg.bitmap.width, height: msg.bitmap.height });
      } else if (msg.type === "render-failed") {
        const p = pending.get(msg.id);
        pending.delete(msg.id);
        p?.reject(Object.assign(new Error(msg.message), { cancelled: msg.cancelled }));
      }
    };
    worker.onerror = () => {
      // The worker itself failed to load: every waiting request falls back to the main thread.
      for (const [, p] of pending) p.reject(Object.assign(new Error("worker failed"), { fallback: true }));
      pending.clear();
      for (const [, w] of openWaiters) w.reject(new Error("worker failed"));
      worker?.terminate();
      worker = null;
    };
  } catch {
    worker = null;
  }
  return worker;
}

function openInWorker(w: Worker, url: string): Promise<number> {
  let p = opened.get(url);
  if (!p) {
    p = new Promise<number>((resolve, reject) => {
      openWaiters.set(url, { resolve, reject });
      // A worker that never answers must not leave pages blank: give up and draw here.
      setTimeout(() => reject(new Error(`the render worker did not open ${url} in ${OPEN_TIMEOUT_MS} ms`)), OPEN_TIMEOUT_MS);
    });
    p.then(() => ready.add(url), () => opened.delete(url));
    opened.set(url, p);
    const absolute = new URL(url, window.location.href).href;
    w.postMessage({ type: "open", doc: url, url: absolute } satisfies ToWorker);
  }
  return p;
}

/**
 * Start the render worker and open the document in it ahead of the first click, in idle time,
 * so the first page you open draws at once instead of waiting for pdf.js to load and parse.
 */
export function warmRenderer(url: string): () => void {
  // In idle time, and only the page-thread document: the worker starts after the first page is
  // drawn (warmLater), so it never competes with it.
  const run = () => void loadDocument(url).catch(() => undefined);
  if (typeof window.requestIdleCallback === "function") {
    const id = window.requestIdleCallback(run, { timeout: 2000 });
    return () => window.cancelIdleCallback(id);
  }
  const id = window.setTimeout(run, 300);
  return () => window.clearTimeout(id);
}

/**
 * Render a page; resolves with a bitmap (from the cache when it is there). `signal` aborts it:
 * a queued page is dropped, a page being drawn is cancelled.
 */
export async function renderPage(r: RenderRequest, signal?: AbortSignal): Promise<Rendered> {
  const k = key(r);
  const hit = cache.get(k);
  if (hit) return hit;
  // The worker draws only once it has the document open. Until then pages are drawn here, and
  // the worker is started in idle time *after* this page: starting it now would make the first
  // page share the CPU with a second pdf.js load and a second parse of the same PDF.
  if (worker && ready.has(r.url)) {
    try {
      const result = await new Promise<Rendered>((resolve, reject) => {
        const id = nextId++;
        pending.set(id, { resolve, reject });
        worker!.postMessage({ type: "render", id, doc: r.url, page: r.page, scale: r.scale, theme: r.theme } satisfies ToWorker);
        signal?.addEventListener("abort", () => worker?.postMessage({ type: "cancel", id } satisfies ToWorker), { once: true });
      });
      remember(k, result);
      drawnBy.worker++;
      return result;
    } catch (e) {
      if (signal?.aborted || (e as { cancelled?: boolean }).cancelled) throw e;
      // Draw it here instead, and say so: a silent fallback would hide a broken worker.
      console.warn(`pdf: page ${r.page} could not be drawn in the worker; drawing it on the main thread`, e);
    }
  }
  const result = await renderOnMainThread(r, signal);
  remember(k, result);
  drawnBy.main++;
  warmLater(r.url);
  return result;
}

const warming = new Set<string>();

/** Start the worker and open the document in it when the browser is idle (once per document). */
function warmLater(url: string) {
  if (warming.has(url)) return;
  warming.add(url);
  const run = () => {
    const w = getWorker();
    if (w) void openInWorker(w, url).catch(() => warming.delete(url));
  };
  if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(run, { timeout: 3000 });
  else window.setTimeout(run, 500);
}

async function renderOnMainThread(r: RenderRequest, signal?: AbortSignal): Promise<Rendered> {
  const doc = await loadDocument(r.url);
  const page = await doc.getPage(r.page);
  const viewport = page.getViewport({ scale: r.scale });
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.floor(viewport.width));
  canvas.height = Math.max(1, Math.floor(viewport.height));
  const task = page.render({
    canvas,
    viewport,
    pageColors: r.theme ? { background: rgb(r.theme.bg), foreground: rgb(r.theme.fg) } : undefined,
  });
  signal?.addEventListener("abort", () => task.cancel(), { once: true });
  await task.promise;
  return { bitmap: canvas, width: canvas.width, height: canvas.height };
}

function rgb(c: [number, number, number]): string {
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

const drawnBy = { worker: 0, main: 0 };

/** Which thread drew the pages so far: "worker", "main-thread", or "mixed" (some fell back). */
export function renderMode(): "worker" | "main-thread" | "mixed" | "none" {
  if (drawnBy.worker && drawnBy.main) return "mixed";
  if (drawnBy.worker) return "worker";
  return drawnBy.main ? "main-thread" : "none";
}

"use client";

import {
  ArrowDown,
  ArrowUp,
  ChevronRight,
  Copy,
  ListTree,
  Maximize,
  PanelLeft,
  Rows3,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import * as React from "react";
import { motion } from "motion/react";
import { createPortal } from "react-dom";
import { ContextMenu, type MenuItem } from "@/components/ui/context-menu";
import { cn } from "@/lib/cn";
import { spring, useSafeMotion } from "@/lib/motion";
import type { PageBox } from "@/lib/pdf";
import { renderMode, renderPage } from "@/lib/pdf-renderer";
import { usePageTheme } from "@/lib/pdf-theme";
import { PageView } from "./page-view";
import { GlassToolbar, Kbd, PageJump, ToolButton, ToolDivider } from "./toolbar";
import { shortcutLabel, useDragPan, useHotkeys, useIdle, usePinchZoom } from "./use-viewer-input";

export interface ReaderHighlight extends PageBox {
  page: number;
}

const GAP = 20;
const PAD_TOP = 76;
const PAD_BOTTOM = 96;
const THUMB_WIDTH = 132;
const THUMB_GAP = 28;

type Size = { width: number; height: number };

/**
 * The whole document, as a reader: continuous pages drawn only near the viewport (and the next
 * ones fetched ahead), a sidebar with page thumbnails, the outline and search results, a
 * floating toolbar, pinch zoom anchored under the fingers, and keyboard shortcuts throughout.
 */
export function PdfReader({
  url,
  doc,
  title,
  initialPage,
  highlights,
  folio,
  initialQuery = "",
  focusSearch = false,
  onClose,
}: {
  url: string;
  doc: PDFDocumentProxy;
  title: string;
  initialPage: number;
  highlights: ReaderHighlight[];
  folio: (page: number) => string | null;
  initialQuery?: string;
  focusSearch?: boolean;
  onClose: (page: number) => void;
}) {
  const total = doc.numPages;
  const theme = usePageTheme();
  const scroller = React.useRef<HTMLDivElement>(null);
  const searchInput = React.useRef<HTMLInputElement>(null);
  const [shown, setShown] = React.useState(false);
  const [sidebar, setSidebar] = React.useState<"pages" | "outline" | "search" | null>(
    focusSearch || initialQuery ? "search" : "pages",
  );
  const [zoom, setZoom] = React.useState(1);
  const [viewport, setViewport] = React.useState({ width: 0, height: 0 });
  const [scrollTop, setScrollTop] = React.useState(0);
  const [current, setCurrent] = React.useState(initialPage);
  const [idle, poke] = useIdle(2400);
  const [menu, setMenu] = React.useState<{ x: number; y: number; selection: string } | null>(null);
  const deskPress = React.useRef<{ x: number; y: number } | null>(null);
  const safe = useSafeMotion(); // reduced motion: these fade instead of moving

  // ---------------------------------------------------------------- page sizes, then layout
  const sizes = React.useRef<Size[]>([]);
  const [sizesVersion, setSizesVersion] = React.useState(0);
  const anchor = React.useRef<{ page: number; within: number } | null>(null);

  React.useEffect(() => {
    let live = true;
    (async () => {
      const first = (await doc.getPage(initialPage)).getViewport({ scale: 1 });
      if (!live) return;
      sizes.current = Array.from({ length: total }, () => ({ width: first.width, height: first.height }));
      setSizesVersion((v) => v + 1);
      // Measure every page in the background, a batch at a time, without blocking a frame.
      for (let start = 1; start <= total && live; start += 24) {
        const end = Math.min(total, start + 23);
        const batch = await Promise.all(
          Array.from({ length: end - start + 1 }, (_, i) =>
            doc.getPage(start + i).then((p) => p.getViewport({ scale: 1 })),
          ),
        );
        if (!live) return;
        let changed = false;
        batch.forEach((v, i) => {
          const s = sizes.current[start - 1 + i]!;
          if (s.width !== v.width || s.height !== v.height) {
            sizes.current[start - 1 + i] = { width: v.width, height: v.height };
            changed = true;
          }
        });
        if (changed) setSizesVersion((v) => v + 1);
        await new Promise((r) => setTimeout(r, 0));
      }
    })().catch(() => undefined);
    return () => {
      live = false;
    };
  }, [doc, total, initialPage]);

  const widest = React.useMemo(
    () => sizes.current.reduce((m, s) => Math.max(m, s.width), 0) || 600,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sizesVersion],
  );
  const fit = viewport.width ? Math.min(1.75, (viewport.width - 64) / widest) : 1;
  const scale = fit * zoom;

  const layout = React.useMemo(() => {
    const offsets = new Float64Array(total + 1);
    let y = PAD_TOP;
    for (let i = 0; i < total; i++) {
      offsets[i] = y;
      y += (sizes.current[i]?.height ?? 0) * scale + GAP;
    }
    offsets[total] = y;
    return { offsets, height: y - GAP + PAD_BOTTOM };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sizesVersion, scale, total]);
  const contentWidth = Math.max(viewport.width, widest * scale + 64);

  const pageAt = React.useCallback(
    (y: number) => {
      const o = layout.offsets;
      let lo = 0;
      let hi = total - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (o[mid]! <= y) lo = mid;
        else hi = mid - 1;
      }
      return lo + 1;
    },
    [layout, total],
  );

  // Keep the page you are reading where it is when sizes above it are corrected.
  React.useLayoutEffect(() => {
    const el = scroller.current;
    const a = anchor.current;
    if (!el || !a) return;
    el.scrollTop = layout.offsets[a.page - 1]! + a.within;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sizesVersion]);
  React.useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const p = pageAt(el.scrollTop + 1);
    anchor.current = { page: p, within: el.scrollTop - layout.offsets[p - 1]! };
  }, [scrollTop, layout, pageAt]);

  React.useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const observer = new ResizeObserver(([e]) =>
      setViewport({ width: e!.contentRect.width, height: e!.contentRect.height }),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // ---------------------------------------------------------------- navigation
  // A page you navigate to (keys, thumbnails, search, page jump) stays the current page until you
  // scroll yourself, even if it is too short to reach the reading line. Zooming and other scrolls
  // made by the reader keep it.
  const pinned = React.useRef<number | null>(null);
  const goTo = React.useCallback(
    (page: number, opts: { smooth?: boolean; y?: number } = {}) => {
      const el = scroller.current;
      if (!el) return;
      const p = Math.min(total, Math.max(1, page));
      pinned.current = p;
      const top = layout.offsets[p - 1]! - 16 + (opts.y ?? 0);
      const far = Math.abs(top - el.scrollTop) > el.clientHeight * 3;
      el.scrollTo({ top, behavior: opts.smooth && !far ? "smooth" : "instant" });
      setCurrent(p);
    },
    [layout, total],
  );

  const opened = React.useRef(false);
  React.useLayoutEffect(() => {
    if (opened.current || !sizesVersion || !viewport.height) return;
    opened.current = true;
    const h = highlights.find((x) => x.page === initialPage);
    const size = sizes.current[initialPage - 1];
    // Open on the cited page, with the highlight a third of the way down the screen.
    const y = h && size && h.space === "unrotated" ? Math.max(0, h.y0 * scale - viewport.height / 3) : 0;
    goTo(initialPage, { y });
    requestAnimationFrame(() => setShown(true));
  }, [sizesVersion, viewport.height, goTo, initialPage, highlights, scale]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    setScrollTop(el.scrollTop);
    // At the very end the last page is the one being read, even when it is too short to reach
    // the reading line (and at the very top, the first): as in native readers.
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 2;
    setCurrent(
      pinned.current ?? (atEnd ? total : el.scrollTop <= 0 ? 1 : pageAt(el.scrollTop + el.clientHeight * 0.4)),
    );
    poke();
  };

  React.useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const release = () => {
      pinned.current = null;
    };
    const onWheel = (e: WheelEvent) => !e.ctrlKey && release(); // ctrl+wheel is a pinch, not a scroll
    const onKey = (e: KeyboardEvent) => ["ArrowUp", "ArrowDown", " "].includes(e.key) && release();
    el.addEventListener("wheel", onWheel, { passive: true });
    el.addEventListener("pointerdown", release);
    el.addEventListener("keydown", onKey);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("pointerdown", release);
      el.removeEventListener("keydown", onKey);
    };
  }, []);

  // ---------------------------------------------------------------- what is drawn
  const first = pageAt(Math.max(0, scrollTop - viewport.height * 0.5));
  const last = Math.min(total, pageAt(scrollTop + viewport.height * 1.5) + 1);
  const visible: number[] = [];
  for (let p = first; p <= last; p++) visible.push(p);

  // Fetch ahead: the next pages (and the one before) are drawn into the cache while you read.
  React.useEffect(() => {
    const t = window.setTimeout(() => {
      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      for (const p of [last + 1, last + 2, last + 3, first - 1]) {
        if (p >= 1 && p <= total) void renderPage({ url, page: p, scale: scale * dpr, theme }).catch(() => undefined);
      }
    }, 180);
    return () => window.clearTimeout(t);
  }, [first, last, scale, theme, url, total]);

  // ---------------------------------------------------------------- zoom
  // The hook keeps zoom inside its limits (and rubber-bands a pinch past them).
  const zoomAt = usePinchZoom(scroller, zoom, setZoom);
  const panning = useDragPan(scroller);
  // Every zoom (keys, buttons, menu, fit width) is anchored, so the page being read stays put.
  const zoomTo = (target: number) => {
    const el = scroller.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    zoomAt(target, box.left + box.width / 2, box.top + box.height / 3);
    poke();
  };
  const zoomBy = (factor: number) => zoomTo(zoom * factor);

  // ---------------------------------------------------------------- search
  const [query, setQuery] = React.useState(initialQuery);
  const [searchOpen, setSearchOpen] = React.useState(focusSearch || !!initialQuery);
  const search = useDocumentSearch(doc, query);
  const [hit, setHit] = React.useState(0);
  const hits = search.hits;
  // A new query starts at the first match on or after the page you are reading, as a browser's
  // find does; once you step through matches, your position is kept as more pages are read.
  const searchFrom = React.useRef<{ page: number; chosen: boolean }>({ page: initialPage, chosen: false });
  React.useEffect(() => {
    searchFrom.current = { page: current, chosen: false };
    setHit(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);
  React.useEffect(() => {
    if (searchFrom.current.chosen || !hits.length) return;
    const at = hits.findIndex((h) => h.page >= searchFrom.current.page);
    if (at >= 0) {
      searchFrom.current.chosen = true;
      setHit(at);
      goTo(hits[at]!.page, { smooth: true });
    } else if (search.done) {
      searchFrom.current.chosen = true;
      setHit(0);
      goTo(hits[0]!.page, { smooth: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hits, search.done]);
  const active = hits.length ? hits[Math.min(hit, hits.length - 1)]! : null;
  const stepHit = (d: number) => {
    if (!hits.length) return;
    searchFrom.current.chosen = true;
    const next = (hit + d + hits.length) % hits.length;
    setHit(next);
    goTo(hits[next]!.page, { smooth: true });
  };
  const openSearch = () => {
    setSearchOpen(true);
    setSidebar((s) => (s ? "search" : s)); // an open sidebar shows the results; a hidden one stays hidden
    requestAnimationFrame(() => searchInput.current?.select());
  };

  // ---------------------------------------------------------------- lifecycle and keys
  const close = React.useCallback(() => onClose(current), [onClose, current]);
  React.useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (focusSearch) requestAnimationFrame(() => searchInput.current?.focus());
    else scroller.current?.focus({ preventScroll: true });
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus?.({ preventScroll: true });
    };
  }, [focusSearch]);

  useHotkeys(true, [
    { combo: "mod+f", run: openSearch, inFields: true },
    { combo: "mod+g", run: () => stepHit(1), inFields: true },
    { combo: "mod+shift+g", run: () => stepHit(-1), inFields: true },
    {
      combo: "escape",
      inFields: true,
      run: () => {
        if (menu) return setMenu(null);
        if (searchOpen && document.activeElement === searchInput.current) {
          setSearchOpen(false);
          scroller.current?.focus({ preventScroll: true });
          return;
        }
        close();
      },
    },
    { combo: "arrowright", run: () => goTo(current + 1, { smooth: true }) },
    { combo: "pagedown", run: () => goTo(current + 1, { smooth: true }) },
    { combo: "arrowleft", run: () => goTo(current - 1, { smooth: true }) },
    { combo: "pageup", run: () => goTo(current - 1, { smooth: true }) },
    { combo: "home", run: () => goTo(1) },
    { combo: "end", run: () => goTo(total) },
    { combo: "mod+=", run: () => zoomBy(1.2) },
    { combo: "mod+-", run: () => zoomBy(1 / 1.2) },
    { combo: "mod+0", run: () => zoomTo(1) },
    { combo: "s", run: () => setSidebar((s) => (s ? null : "pages")) },
  ]);

  const menuItems: MenuItem[] = [
    {
      label: "Copy",
      hint: shortcutLabel("mod+c"),
      icon: <Copy aria-hidden />,
      disabled: !menu?.selection,
      run: () => void navigator.clipboard?.writeText(menu?.selection ?? ""),
    },
    {
      label: menu?.selection ? `Search for “${truncate(menu.selection, 24)}”` : "Search the document",
      hint: shortcutLabel("mod+f"),
      icon: <Search aria-hidden />,
      run: () => {
        if (menu?.selection) setQuery(menu.selection.trim());
        openSearch();
      },
    },
    { label: "Zoom in", hint: shortcutLabel("mod+="), icon: <ZoomIn aria-hidden />, run: () => zoomBy(1.2) },
    { label: "Zoom out", hint: shortcutLabel("mod+-"), icon: <ZoomOut aria-hidden />, run: () => zoomBy(1 / 1.2) },
    { label: "Fit width", hint: shortcutLabel("mod+0"), icon: <Maximize aria-hidden />, run: () => zoomTo(1) },
  ];

  const printed = folio(current);
  const content = (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label={`${title}: document reader`}
      data-testid="pdf-reader"
      data-current-page={current}
      data-render-mode={renderMode()}
      // Opens once it is on the right page (shown); leaves the way it came. Reduced motion: fade.
      initial={safe({ opacity: 0, scale: 0.985 })}
      animate={safe(shown ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.985 })}
      exit={safe({ opacity: 0, scale: 0.985 })}
      transition={spring.modal}
      className="fixed inset-0 z-[60] flex flex-col bg-[var(--pdf-desk)]"
    >
      <header className="absolute inset-x-0 top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-glass px-3 backdrop-blur-xl backdrop-saturate-150">
        <ToolButton label={sidebar ? "Hide sidebar" : "Show sidebar"} shortcut="s" pressed={!!sidebar} onClick={() => setSidebar((s) => (s ? null : "pages"))}>
          <PanelLeft aria-hidden />
        </ToolButton>
        <div className="min-w-0">
          <p className="truncate text-[0.84375rem] font-semibold tracking-[-0.01em] text-ink">{title}</p>
          <p className="num text-[0.71875rem] text-ink-3" data-testid="reader-page-label" aria-live="polite">
            PDF p. {current}
            {printed ? ` · printed p. ${printed}` : ""} of {total}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          {searchOpen ? (
            <SearchBox
              ref={searchInput}
              query={query}
              onQuery={setQuery}
              status={search}
              index={active ? Math.min(hit, hits.length - 1) + 1 : 0}
              onStep={stepHit}
              onClose={() => {
                setSearchOpen(false);
                setQuery("");
              }}
            />
          ) : (
            <ToolButton label="Search the document" shortcut="mod+f" onClick={openSearch}>
              <Search aria-hidden />
            </ToolButton>
          )}
          <ToolButton label="Close reader" shortcut="Esc" onClick={close} data-testid="reader-close">
            <X aria-hidden />
          </ToolButton>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        <aside
          aria-label="Document navigation"
          className={cn(
            "z-20 mt-14 flex shrink-0 flex-col overflow-hidden border-r border-line bg-surface/80 backdrop-blur-xl",
            sidebar ? "w-[220px] animate-[fade-in_180ms_ease-out] motion-reduce:animate-none" : "w-0 border-r-0",
          )}
        >
          <div className="flex shrink-0 gap-1 border-b border-line p-1.5" role="tablist" aria-label="Sidebar">
            {(
              [
                ["pages", "Pages", Rows3],
                ["outline", "Outline", ListTree],
                ["search", "Search", Search],
              ] as const
            ).map(([id, label, Icon]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={sidebar === id}
                onClick={() => {
                  setSidebar(id);
                  if (id === "search") openSearch();
                }}
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-[0.75rem] font-medium transition-colors",
                  sidebar === id ? "bg-ink/[0.07] text-ink" : "text-ink-3 hover:text-ink-2",
                )}
              >
                <Icon aria-hidden className="size-3.5" />
                {label}
              </button>
            ))}
          </div>
          {sidebar === "pages" ? (
            <Thumbnails
              url={url}
              doc={doc}
              sizes={sizes.current}
              version={sizesVersion}
              current={current}
              theme={theme}
              folio={folio}
              cited={new Set(highlights.map((h) => h.page))}
              onPick={(p) => goTo(p)}
            />
          ) : sidebar === "outline" ? (
            <Outline doc={doc} current={current} onPick={(p) => goTo(p)} />
          ) : sidebar === "search" ? (
            <SearchResults status={search} query={query} active={active} onPick={(i) => ((searchFrom.current.chosen = true), setHit(i), goTo(hits[i]!.page))} />
          ) : null}
        </aside>

        <div
          ref={scroller}
          tabIndex={-1}
          onScroll={onScroll}
          onPointerMove={poke}
          // Click off the document: a plain click on the desk around the pages closes the reader
          // (not a drag, a pan, a text selection, or a click on a page).
          onPointerDown={(e) => {
            deskPress.current = e.target === e.currentTarget || e.target === e.currentTarget.firstElementChild
              ? { x: e.clientX, y: e.clientY }
              : null;
          }}
          onClick={(e) => {
            const press = deskPress.current;
            deskPress.current = null;
            if (!press || panning || e.button !== 0) return;
            if (Math.hypot(e.clientX - press.x, e.clientY - press.y) > 5) return;
            if (window.getSelection()?.toString()) return;
            close();
          }}
          data-click-off="close"
          onContextMenu={(e) => {
            e.preventDefault();
            setMenu({ x: e.clientX, y: e.clientY, selection: window.getSelection()?.toString() ?? "" });
          }}
          data-testid="reader-scroller"
          className={cn(
            "pdf-stage relative min-w-0 flex-1 overflow-auto overscroll-contain outline-none",
            panning && "cursor-grab active:cursor-grabbing [&_.textLayer_span]:cursor-grab",
          )}
        >
          <div className="relative" style={{ height: layout.height, width: contentWidth }}>
            {sizesVersion
              ? visible.map((p) => {
                  const size = sizes.current[p - 1]!;
                  const left = Math.max(32, (contentWidth - size.width * scale) / 2);
                  const onPage = active?.page === p ? active.index : -1;
                  return (
                    <div key={p} className="absolute" style={{ top: layout.offsets[p - 1], left }}>
                      <PageView
                        url={url}
                        doc={doc}
                        page={p}
                        scale={scale}
                        size={size}
                        theme={theme}
                        highlights={highlights.filter((h) => h.page === p)}
                        query={query.trim().length >= 2 ? query : ""}
                        activeMatch={onPage}
                        className="rounded-[3px]"
                      />
                    </div>
                  );
                })
              : null}
          </div>
        </div>

        <GlassToolbar idle={idle} className="bottom-6" label="Reader controls">
          <ToolButton label="Previous page" shortcut="arrowleft" disabled={current <= 1} onClick={() => goTo(current - 1, { smooth: true })}>
            <ArrowUp aria-hidden />
          </ToolButton>
          <PageJump page={current} total={total} onJump={(p) => goTo(p)} />
          <ToolButton label="Next page" shortcut="arrowright" disabled={current >= total} onClick={() => goTo(current + 1, { smooth: true })}>
            <ArrowDown aria-hidden />
          </ToolButton>
          <ToolDivider />
          <ToolButton label="Zoom out" shortcut="mod+-" onClick={() => zoomBy(1 / 1.2)} disabled={zoom <= 0.5}>
            <ZoomOut aria-hidden />
          </ToolButton>
          <button
            type="button"
            onClick={() => zoomTo(1)}
            aria-label="Fit width"
            className="num h-8 w-12 rounded-xl text-[0.75rem] font-medium text-ink-2 hover:bg-ink/[0.06] hover:text-ink"
          >
            {Math.round(zoom * 100)}%
          </button>
          <ToolButton label="Zoom in" shortcut="mod+=" onClick={() => zoomBy(1.2)} disabled={zoom >= 4}>
            <ZoomIn aria-hidden />
          </ToolButton>
        </GlassToolbar>
      </div>
      <ContextMenu at={menu} items={menuItems} onClose={() => setMenu(null)} />
    </motion.div>
  );
  return typeof document === "undefined" ? null : createPortal(content, document.body);
}

function truncate(s: string, n: number) {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
}

// -------------------------------------------------------------------------------- thumbnails

function Thumbnails({
  url,
  doc,
  sizes,
  version,
  current,
  theme,
  folio,
  cited,
  onPick,
}: {
  url: string;
  doc: PDFDocumentProxy;
  sizes: Size[];
  version: number;
  current: number;
  theme: ReturnType<typeof usePageTheme>;
  folio: (page: number) => string | null;
  cited: Set<number>;
  onPick: (page: number) => void;
}) {
  const box = React.useRef<HTMLDivElement>(null);
  const [top, setTop] = React.useState(0);
  const [height, setHeight] = React.useState(600);
  const offsets = React.useMemo(() => {
    const o = new Float64Array(sizes.length + 1);
    let y = 12;
    sizes.forEach((s, i) => {
      o[i] = y;
      y += (s.height / s.width) * THUMB_WIDTH + THUMB_GAP;
    });
    o[sizes.length] = y;
    return o;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sizes, version]);

  React.useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(([e]) => setHeight(e!.contentRect.height));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // The mini-map follows the reader: the current page's thumbnail is kept in view.
  React.useEffect(() => {
    const el = box.current;
    if (!el || !sizes.length) return;
    const y0 = offsets[current - 1]!;
    const y1 = offsets[current]! - THUMB_GAP;
    if (y0 < el.scrollTop + 8 || y1 > el.scrollTop + el.clientHeight - 8) {
      el.scrollTo({ top: y0 - el.clientHeight / 2 + (y1 - y0) / 2, behavior: "instant" });
    }
  }, [current, offsets, sizes.length]);

  const items: number[] = [];
  for (let p = 1; p <= sizes.length; p++) {
    if (offsets[p]! >= top - 400 && offsets[p - 1]! <= top + height + 400) items.push(p);
  }
  return (
    <div ref={box} onScroll={(e) => setTop(e.currentTarget.scrollTop)} className="relative min-h-0 flex-1 overflow-y-auto" data-testid="reader-thumbnails">
      <div className="relative" style={{ height: offsets[sizes.length] }}>
        {items.map((p) => {
          const s = sizes[p - 1]!;
          const on = p === current;
          return (
            <button
              key={p}
              type="button"
              onClick={() => onPick(p)}
              aria-label={`Page ${p}`}
              aria-current={on ? "page" : undefined}
              className="group absolute left-1/2 flex -translate-x-1/2 flex-col items-center gap-1.5"
              style={{ top: offsets[p - 1] }}
            >
              <span
                className={cn(
                  "block rounded-[3px] ring-offset-2 ring-offset-surface transition-shadow",
                  on ? "ring-2 ring-accent" : "ring-1 ring-line group-hover:ring-line-strong",
                )}
              >
                <PageView
                  url={url}
                  doc={doc}
                  page={p}
                  scale={THUMB_WIDTH / s.width}
                  size={s}
                  theme={theme}
                  textLayer={false}
                  settleMs={0}
                  label={`Thumbnail of page ${p}`}
                  className="rounded-[3px] shadow-none"
                />
              </span>
              <span className={cn("num flex items-center gap-1 text-[0.6875rem]", on ? "font-semibold text-ink" : "text-ink-3")}>
                {cited.has(p) ? <span aria-label="cited" className="size-1.5 rounded-full bg-amber" /> : null}
                {p}
                {folio(p) ? <span className="text-ink-3">· {folio(p)}</span> : null}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// -------------------------------------------------------------------------------- outline

interface OutlineNode {
  title: string;
  page: number | null;
  items: OutlineNode[];
}

function Outline({ doc, current, onPick }: { doc: PDFDocumentProxy; current: number; onPick: (page: number) => void }) {
  const [nodes, setNodes] = React.useState<OutlineNode[] | null>(null);
  React.useEffect(() => {
    let live = true;
    const resolve = async (dest: unknown): Promise<number | null> => {
      try {
        const explicit = typeof dest === "string" ? await doc.getDestination(dest) : dest;
        if (!Array.isArray(explicit) || explicit[0] == null) return null;
        const ref = explicit[0];
        return typeof ref === "number" ? ref + 1 : (await doc.getPageIndex(ref)) + 1;
      } catch {
        return null;
      }
    };
    type Raw = { title: string; dest: unknown; items: Raw[] };
    const walk = (items: Raw[]): Promise<OutlineNode[]> =>
      Promise.all(items.map(async (i) => ({ title: i.title, page: await resolve(i.dest), items: await walk(i.items ?? []) })));
    doc.getOutline().then(
      async (raw) => live && setNodes(raw ? await walk(raw as unknown as Raw[]) : []),
      () => live && setNodes([]),
    );
    return () => {
      live = false;
    };
  }, [doc]);

  if (nodes === null) return <p className="p-4 text-[0.75rem] text-ink-3">Reading the outline…</p>;
  if (!nodes.length) {
    return (
      <p className="p-4 text-[0.75rem] leading-relaxed text-ink-3" data-testid="reader-outline-empty">
        This PDF has no outline (bookmarks). Use the page thumbnails or search instead.
      </p>
    );
  }
  // The section you are in: the last outline entry that starts on or before the current page.
  const flat: OutlineNode[] = [];
  const collect = (ns: OutlineNode[]) => ns.forEach((n) => (flat.push(n), collect(n.items)));
  collect(nodes);
  const here = flat.filter((n) => n.page !== null && n.page <= current).at(-1) ?? null;
  return (
    <ul className="min-h-0 flex-1 overflow-y-auto p-1.5 text-[0.78125rem]" data-testid="reader-outline">
      {nodes.map((n, i) => (
        <OutlineItem key={i} node={n} depth={0} here={here} onPick={onPick} />
      ))}
    </ul>
  );
}

function OutlineItem({ node, depth, here, onPick }: { node: OutlineNode; depth: number; here: OutlineNode | null; onPick: (p: number) => void }) {
  const [open, setOpen] = React.useState(depth === 0);
  const on = node === here;
  return (
    <li>
      <div className={cn("flex items-center rounded-lg", on ? "bg-accent-soft text-accent" : "text-ink-2 hover:bg-ink/[0.05]")} style={{ paddingLeft: depth * 12 }}>
        {node.items.length ? (
          <button type="button" aria-label={open ? "Collapse" : "Expand"} aria-expanded={open} onClick={() => setOpen((v) => !v)} className="p-1 text-ink-3">
            <ChevronRight aria-hidden className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          </button>
        ) : (
          <span className="w-[22px]" />
        )}
        <button
          type="button"
          disabled={node.page === null}
          onClick={() => node.page && onPick(node.page)}
          className="flex min-w-0 flex-1 items-baseline justify-between gap-2 py-1.5 pr-2 text-left"
        >
          <span className="truncate">{node.title}</span>
          {node.page ? <span className="num shrink-0 text-[0.6875rem] text-ink-3">{node.page}</span> : null}
        </button>
      </div>
      {open && node.items.length ? (
        <ul>
          {node.items.map((c, i) => (
            <OutlineItem key={i} node={c} depth={depth + 1} here={here} onPick={onPick} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

// -------------------------------------------------------------------------------- search

interface SearchStatus {
  hits: { page: number; index: number; snippet: string }[];
  searched: number;
  total: number;
  done: boolean;
}

const textCache = new WeakMap<PDFDocumentProxy, Map<number, Promise<string[]>>>();

function pageStrings(doc: PDFDocumentProxy, page: number): Promise<string[]> {
  let byPage = textCache.get(doc);
  if (!byPage) textCache.set(doc, (byPage = new Map()));
  let p = byPage.get(page);
  if (!p) {
    p = doc
      .getPage(page)
      .then((pg) => pg.getTextContent({ includeMarkedContent: false, disableNormalization: true }))
      .then((tc) => tc.items.map((i) => ("str" in i ? i.str : "")));
    byPage.set(page, p);
  }
  return p;
}

/**
 * Search every page's text (in pdf.js's worker), progressively: matches arrive page by page and
 * the reader can jump to the first one before the last page is read. Matching is per text item,
 * exactly as the page marks are drawn, so counts and marks agree.
 */
function useDocumentSearch(doc: PDFDocumentProxy, query: string): SearchStatus {
  const [status, setStatus] = React.useState<SearchStatus>({ hits: [], searched: 0, total: doc.numPages, done: true });
  React.useEffect(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (needle.length < 2) {
      setStatus({ hits: [], searched: 0, total: doc.numPages, done: true });
      return;
    }
    let live = true;
    const t = window.setTimeout(async () => {
      const hits: SearchStatus["hits"] = [];
      for (let p = 1; p <= doc.numPages && live; p++) {
        const strings = await pageStrings(doc, p);
        let index = 0;
        for (const s of strings) {
          const lower = s.toLocaleLowerCase();
          for (let at = lower.indexOf(needle); at >= 0; at = lower.indexOf(needle, at + needle.length)) {
            const from = Math.max(0, at - 32);
            hits.push({ page: p, index: index++, snippet: `${from > 0 ? "…" : ""}${s.slice(from, at + needle.length + 48)}` });
          }
        }
        if (p % 12 === 0 || p === doc.numPages) {
          if (!live) return;
          setStatus({ hits: [...hits], searched: p, total: doc.numPages, done: p === doc.numPages });
          await new Promise((r) => setTimeout(r, 0));
        }
      }
    }, 0);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [doc, query]);
  return status;
}

const SearchBox = React.forwardRef<
  HTMLInputElement,
  {
    query: string;
    onQuery: (q: string) => void;
    status: SearchStatus;
    index: number;
    onStep: (d: number) => void;
    onClose: () => void;
  }
>(function SearchBox({ query, onQuery, status, index, onStep, onClose }, ref) {
  return (
    <div className="flex h-9 items-center gap-1 rounded-xl border border-line bg-surface pl-2.5 pr-1 shadow-[var(--shadow-card)] focus-within:border-accent/50">
      <Search aria-hidden className="size-4 shrink-0 text-ink-3" />
      <input
        ref={ref}
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onStep(e.shiftKey ? -1 : 1);
          }
        }}
        placeholder="Search the document"
        aria-label="Search the document"
        data-testid="reader-search"
        className="h-full w-52 bg-transparent text-[0.8125rem] text-ink outline-none placeholder:text-ink-3"
      />
      <span className="num min-w-14 text-right text-[0.71875rem] text-ink-3" aria-live="polite" data-testid="reader-search-count">
        {query.trim().length < 2 ? "" : status.hits.length ? `${index} of ${status.hits.length}${status.done ? "" : "+"}` : status.done ? "No matches" : "Searching…"}
      </span>
      <ToolButton label="Previous match" shortcut="mod+shift+g" onClick={() => onStep(-1)} disabled={!status.hits.length} className="size-7">
        <ArrowUp aria-hidden />
      </ToolButton>
      <ToolButton label="Next match" shortcut="mod+g" onClick={() => onStep(1)} disabled={!status.hits.length} className="size-7">
        <ArrowDown aria-hidden />
      </ToolButton>
      <ToolButton label="Close search" onClick={onClose} className="size-7">
        <X aria-hidden />
      </ToolButton>
    </div>
  );
});

function SearchResults({
  status,
  query,
  active,
  onPick,
}: {
  status: SearchStatus;
  query: string;
  active: SearchStatus["hits"][number] | null;
  onPick: (i: number) => void;
}) {
  if (query.trim().length < 2) {
    return (
      <p className="p-4 text-[0.75rem] leading-relaxed text-ink-3">
        Type at least two characters. <Kbd>{shortcutLabel("mod+f")}</Kbd> opens search from anywhere in the reader.
      </p>
    );
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <p className="num shrink-0 border-b border-line px-3 py-2 text-[0.71875rem] text-ink-3">
        {status.hits.length} match{status.hits.length === 1 ? "" : "es"}
        {status.done ? "" : ` · reading p. ${status.searched} of ${status.total}`}
      </p>
      <ul className="min-h-0 flex-1 overflow-y-auto p-1.5" data-testid="reader-search-results">
        {status.hits.slice(0, 500).map((h, i) => (
          <li key={`${h.page}-${h.index}`}>
            <button
              type="button"
              onClick={() => onPick(i)}
              className={cn(
                "w-full rounded-lg px-2.5 py-2 text-left text-[0.75rem] leading-snug",
                active === h ? "bg-accent-soft text-ink" : "text-ink-2 hover:bg-ink/[0.05]",
              )}
            >
              <span className="num mb-0.5 block text-[0.65625rem] font-semibold uppercase tracking-[0.06em] text-ink-3">Page {h.page}</span>
              {h.snippet}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

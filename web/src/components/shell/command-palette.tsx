"use client";

import {
  ArrowRight,
  BookOpen,
  CornerDownLeft,
  FileText,
  Hash,
  LayoutDashboard,
  Link2,
  Monitor,
  Moon,
  PanelLeft,
  Search,
  ShieldCheck,
  Sigma,
  Sun,
  Table2,
  Upload,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { createPortal } from "react-dom";
import { Kbd } from "@/components/pdf/toolbar";
import { shortcutLabel, useHotkeys } from "@/components/pdf/use-viewer-input";
import { reportTitle, statusMeta, whenAdded } from "@/components/shell/report-meta";
import { useShell } from "@/components/shell/shell-context";
import { useTheme } from "@/components/shell/theme";
import { useUpload } from "@/components/shell/upload";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { spring } from "@/lib/motion";
import { usePrefetchReport, useReports } from "@/lib/queries";

interface Command {
  id: string;
  group: string;
  label: string;
  detail?: string;
  keywords?: string;
  icon: React.ReactNode;
  shortcut?: string;
  run: () => void;
  onActive?: () => void;
}

const PaletteContext = React.createContext<{ open: (query?: string) => void }>({ open: () => undefined });
export const usePalette = () => React.useContext(PaletteContext);

/**
 * Subsequence match with a score: characters that start words or follow each other score more,
 * so "uni" finds "Unilever" before "community". Returns the matched positions for highlighting.
 */
export function fuzzy(text: string, query: string): { score: number; hits: number[] } | null {
  const t = text.toLowerCase();
  const q = query.toLowerCase().trim();
  if (!q) return { score: 0, hits: [] };
  const direct = t.indexOf(q);
  if (direct >= 0) {
    const atWord = direct === 0 || /[\s\-_/.(]/.test(t[direct - 1]!);
    return { score: 100 - direct + (atWord ? 50 : 0) + q.length * 2, hits: [...q].map((_, i) => direct + i) };
  }
  const hits: number[] = [];
  let score = 0;
  let at = 0;
  for (const ch of q) {
    if (ch === " ") continue;
    const i = t.indexOf(ch, at);
    if (i < 0) return null;
    score += i === at ? 6 : 1;
    if (i === 0 || /[\s\-_/.(]/.test(t[i - 1]!)) score += 8;
    hits.push(i);
    at = i + 1;
  }
  return { score, hits };
}

function Highlighted({ text, hits }: { text: string; hits: number[] }) {
  if (!hits.length) return <>{text}</>;
  const set = new Set(hits);
  return (
    <>
      {[...text].map((ch, i) =>
        set.has(i) ? (
          <mark key={i} className="bg-transparent font-semibold text-ink">
            {ch}
          </mark>
        ) : (
          <React.Fragment key={i}>{ch}</React.Fragment>
        ),
      )}
    </>
  );
}

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<{ open: boolean; query: string }>({ open: false, query: "" });
  const open = React.useCallback((query = "") => setState({ open: true, query }), []);
  useHotkeys(true, [{ combo: "mod+k", inFields: true, run: () => setState((s) => ({ open: !s.open, query: "" })) }]);
  return (
    <PaletteContext.Provider value={React.useMemo(() => ({ open }), [open])}>
      {children}
      <AnimatePresence>
        {state.open ? <Palette key="palette" initial={state.query} onClose={() => setState({ open: false, query: "" })} /> : null}
      </AnimatePresence>
    </PaletteContext.Provider>
  );
}

function Palette({ initial, onClose }: { initial: string; onClose: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const reports = useReports();
  const prefetch = usePrefetchReport();
  const { setTheme, theme } = useTheme();
  const { toggleSidebar } = useShell();
  const upload = useUpload();
  const toast = useToast();
  const [query, setQuery] = React.useState(initial);
  const [active, setActive] = React.useState(0);
  const list = React.useRef<HTMLDivElement>(null);
  const restore = React.useRef<HTMLElement | null>(null);

  React.useEffect(() => {
    restore.current = document.activeElement as HTMLElement | null;
    return () => restore.current?.focus?.({ preventScroll: true });
  }, []);

  const onReport = /^\/reports\/(\d+)/.exec(pathname ?? "")?.[1] ?? null;
  const go = (href: string) => () => router.push(href);
  const scrollTo = (id: string) => () => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  const commands: Command[] = React.useMemo(() => {
    const out: Command[] = [];
    for (const r of reports.data ?? []) {
      const s = statusMeta(r.status);
      out.push({
        id: `report-${r.id}`,
        group: "Reports",
        label: reportTitle(r),
        detail: [r.period_label ? `FY ${r.period_label}` : null, s.label, whenAdded(r.created_at)].filter(Boolean).join(" · "),
        keywords: `${r.filename} ${r.id} ${r.document_type}`,
        icon: <FileText aria-hidden />,
        run: go(`/reports/${r.id}`),
        onActive: () => prefetch(r.id),
      });
    }
    const n = query.trim().replace(/^#/, "");
    if (/^\d+$/.test(n)) {
      out.unshift({
        id: "open-number",
        group: "Reports",
        label: `Open report ${n}`,
        icon: <Hash aria-hidden />,
        run: go(`/reports/${n}`),
        onActive: () => prefetch(n),
      });
    }
    if (onReport) {
      out.push(
        { id: "sec-figures", group: "This report", label: "Key figures", icon: <Table2 aria-hidden />, run: scrollTo("figures") },
        { id: "sec-ratios", group: "This report", label: "Ratios", icon: <Sigma aria-hidden />, run: scrollTo("ratios") },
        { id: "sec-commentary", group: "This report", label: "Commentary", icon: <BookOpen aria-hidden />, run: scrollTo("commentary") },
        {
          id: "open-doc",
          group: "This report",
          label: "Open the original document",
          keywords: "pdf reader viewer",
          icon: <BookOpen aria-hidden />,
          run: () => {
            const button = document.querySelector<HTMLButtonElement>("[data-testid=open-reader]");
            if (button) button.click();
            else toast({ tone: "info", title: "Select a figure first", body: "Click a page chip to open its page, then open the document." });
          },
        },
        {
          id: "copy-link",
          group: "This report",
          label: "Copy link to this report",
          icon: <Link2 aria-hidden />,
          run: () => {
            void navigator.clipboard?.writeText(window.location.href.split("#")[0]!);
            toast({ tone: "ok", title: "Link copied" });
          },
        },
      );
    }
    out.push(
      { id: "nav-dashboard", group: "Go to", label: "Dashboard", keywords: "home reports", icon: <LayoutDashboard aria-hidden />, run: go("/") },
      { id: "nav-limits", group: "Go to", label: "Method & limits", keywords: "limitations", icon: <ShieldCheck aria-hidden />, run: go("/limitations") },
      { id: "act-upload", group: "Actions", label: "Analyse a new report…", keywords: "upload pdf new", icon: <Upload aria-hidden />, run: upload.pick },
      { id: "act-sidebar", group: "Actions", label: "Toggle sidebar", icon: <PanelLeft aria-hidden />, shortcut: "mod+\\", run: toggleSidebar },
      { id: "theme-light", group: "Theme", label: "Light", detail: theme === "light" ? "Current" : undefined, keywords: "theme appearance", icon: <Sun aria-hidden />, run: () => setTheme("light") },
      { id: "theme-dark", group: "Theme", label: "Dark", detail: theme === "dark" ? "Current" : undefined, keywords: "theme appearance", icon: <Moon aria-hidden />, run: () => setTheme("dark") },
      { id: "theme-system", group: "Theme", label: "Match system", detail: theme === "system" ? "Current" : undefined, keywords: "theme appearance auto", icon: <Monitor aria-hidden />, run: () => setTheme("system") },
    );
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reports.data, query, onReport, theme]);

  const results = React.useMemo(() => {
    if (!query.trim()) {
      // Nothing typed: the five newest reports, then everything else.
      const recent = commands.filter((c) => c.group === "Reports").slice(0, 5);
      return [...recent.map((c) => ({ c: { ...c, group: "Recent" }, hits: [] as number[] })), ...commands.filter((c) => c.group !== "Reports").map((c) => ({ c, hits: [] as number[] }))];
    }
    return commands
      .map((c) => {
        const onLabel = fuzzy(c.label, query);
        const onWords = onLabel ? null : fuzzy(`${c.keywords ?? ""} ${c.group}`, query);
        const m = onLabel ?? (onWords ? { score: onWords.score - 20, hits: [] } : null);
        return m ? { c, hits: m.hits, score: m.score } : null;
      })
      .filter((x): x is { c: Command; hits: number[]; score: number } => x !== null)
      .sort((a, b) => b.score - a.score)
      .slice(0, 40);
  }, [commands, query]);

  React.useEffect(() => setActive(0), [query]);
  React.useEffect(() => {
    results[active]?.c.onActive?.();
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, results]);

  const run = (i: number) => {
    const r = results[i];
    if (!r) return;
    onClose();
    r.c.run();
  };

  const groups: { name: string; items: { c: Command; hits: number[]; index: number }[] }[] = [];
  results.forEach((r, index) => {
    const g = groups.find((x) => x.name === r.c.group) ?? (groups.push({ name: r.c.group, items: [] }), groups.at(-1)!);
    g.items.push({ ...r, index });
  });

  return createPortal(
    <motion.div
      className="fixed inset-0 z-[75] flex items-start justify-center px-4 pt-[12vh]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.12 } }}
      transition={{ duration: 0.14 }}
    >
      <div aria-hidden className="absolute inset-0 bg-[oklch(0.15_0.02_262/0.28)] backdrop-blur-[3px]" onClick={onClose} />
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        data-testid="command-palette"
        initial={{ opacity: 0, scale: 0.97, y: -8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: -4, transition: { duration: 0.12 } }}
        transition={spring.modal}
        className="relative flex max-h-[min(560px,70vh)] w-full max-w-[640px] flex-col overflow-hidden rounded-2xl border border-line-strong/70 bg-surface-raised/95 shadow-[var(--shadow-pop)] backdrop-blur-2xl"
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search aria-hidden className="size-[18px] shrink-0 text-ink-3" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" || (e.ctrlKey && e.key === "n")) {
                e.preventDefault();
                setActive((a) => (results.length ? (a + 1) % results.length : 0));
              } else if (e.key === "ArrowUp" || (e.ctrlKey && e.key === "p")) {
                e.preventDefault();
                setActive((a) => (results.length ? (a - 1 + results.length) % results.length : 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(active);
              } else if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                if (query) setQuery("");
                else onClose();
              }
            }}
            placeholder="Search reports, jump to a section, run a command…"
            aria-label="Command"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-activedescendant={results[active] ? `palette-${results[active]!.c.id}` : undefined}
            data-testid="palette-input"
            className="h-14 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-3"
          />
          <Kbd>Esc</Kbd>
        </div>
        <div ref={list} id="palette-list" role="listbox" className="min-h-0 flex-1 overflow-y-auto p-1.5">
          {groups.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-6 py-12 text-center" data-testid="palette-empty">
              <Search aria-hidden className="size-5 text-ink-3" />
              <p className="text-[13.5px] font-medium text-ink">Nothing matches “{query}”</p>
              <p className="text-[12.5px] text-ink-3">Try a company name, a report number, or a command like “theme”.</p>
              <button
                type="button"
                onClick={() => (onClose(), upload.pick())}
                className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-[12.5px] font-medium text-ink hover:bg-surface-sunk"
              >
                <Upload aria-hidden className="size-3.5" />
                Analyse a new report
              </button>
            </div>
          ) : (
            groups.map((g) => (
              <div key={g.name} role="group" aria-label={g.name} className="pb-1">
                <p className="eyebrow px-2.5 pb-1 pt-2.5">{g.name}</p>
                {g.items.map(({ c, hits, index }) => (
                  <div
                    key={c.id}
                    id={`palette-${c.id}`}
                    role="option"
                    aria-selected={index === active}
                    data-index={index}
                    data-testid="palette-item"
                    onPointerMove={() => index !== active && setActive(index)}
                    onClick={() => run(index)}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2 text-[13.5px] transition-colors duration-75",
                      index === active ? "bg-accent-soft text-ink" : "text-ink-2",
                    )}
                  >
                    <span
                      className={cn(
                        "flex size-7 shrink-0 items-center justify-center rounded-lg border [&_svg]:size-[15px]",
                        index === active ? "border-accent/30 bg-surface text-accent" : "border-line bg-surface-sunk text-ink-3",
                      )}
                    >
                      {c.icon}
                    </span>
                    <span className="min-w-0 flex-1 truncate">
                      <Highlighted text={c.label} hits={hits} />
                      {c.detail ? <span className="ml-2 text-[12px] text-ink-3">{c.detail}</span> : null}
                    </span>
                    {c.shortcut ? <Kbd>{c.shortcut.includes("+") ? shortcutLabel(c.shortcut) : c.shortcut}</Kbd> : null}
                    {index === active ? <CornerDownLeft aria-hidden className="size-3.5 text-ink-3" /> : null}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
        <div className="flex items-center gap-4 border-t border-line bg-surface-sunk/60 px-4 py-2 text-[11.5px] text-ink-3">
          <span className="inline-flex items-center gap-1.5">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> move
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Kbd>↵</Kbd> open
          </span>
          <span className="ml-auto inline-flex items-center gap-1">
            <ArrowRight aria-hidden className="size-3" /> {reports.data?.length ?? 0} reports
          </span>
        </div>
      </motion.div>
    </motion.div>,
    document.body,
  );
}

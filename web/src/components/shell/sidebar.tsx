"use client";

import { Copy, ExternalLink, FlaskConical, LayoutDashboard, Link2, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Plus, Search, ShieldCheck, Sun } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { BrandMark } from "@/components/brand-mark";
import { Kbd } from "@/components/pdf/toolbar";
import { shortcutLabel } from "@/components/pdf/use-viewer-input";
import { usePalette } from "@/components/shell/command-palette";
import { reportTitle, statusMeta } from "@/components/shell/report-meta";
import { useShell } from "@/components/shell/shell-context";
import { type ThemeChoice, useTheme } from "@/components/shell/theme";
import { useUpload } from "@/components/shell/upload";
import { ContextMenu, type MenuItem } from "@/components/ui/context-menu";
import { useToast } from "@/components/ui/toast";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { spring } from "@/lib/motion";
import { type ReportSummary, usePrefetchReport, useReports, useShowSamples } from "@/lib/queries";

export const SIDEBAR_WIDE = 248;
export const SIDEBAR_NARROW = 60;

/**
 * The fixed sidebar: product, search, the dashboard, recent reports and settings. Collapses to an
 * icon rail (⌘\); every row is 32 px with its icon in a 20 px box at the same x in both widths.
 * Arrow keys move between rows; hovering a report fetches it so opening it is instant.
 */
export function Sidebar({ mobile = false }: { mobile?: boolean }) {
  const { collapsed: rail, toggleSidebar, setDrawer } = useShell();
  const collapsed = rail && !mobile;
  const pathname = usePathname() ?? "/";
  const palette = usePalette();
  const upload = useUpload();
  const reports = useReports();
  const [showSamples] = useShowSamples();
  const listed = (reports.data ?? []).filter((r) => showSamples || !r.is_sample);
  const nav = React.useRef<HTMLElement>(null);

  // Arrow keys move focus between rows, like a native source list.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const rows = [...(nav.current?.querySelectorAll<HTMLElement>("[data-nav-row]") ?? [])];
    const i = rows.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    e.preventDefault();
    rows[(i + (e.key === "ArrowDown" ? 1 : rows.length - 1)) % rows.length]?.focus();
  };

  return (
    <aside
      aria-label="Sidebar"
      data-testid="sidebar"
      data-collapsed={collapsed ? "true" : "false"}
      style={{ width: mobile ? SIDEBAR_WIDE : collapsed ? SIDEBAR_NARROW : SIDEBAR_WIDE }}
      className="flex h-full shrink-0 flex-col overflow-hidden border-r border-line bg-surface-sunk/80 backdrop-blur-xl"
      onClick={(e) => mobile && (e.target as HTMLElement).closest("a") && setDrawer(false)}
    >
      <div className="flex h-14 shrink-0 items-center gap-2 px-3">
        <Link href="/" className="flex min-w-0 items-center gap-2.5 rounded-lg px-1 py-1" aria-label="FinIntel dashboard">
          <BrandMark className="size-7 shrink-0" />
          {!collapsed ? <span className="truncate text-[0.9375rem] font-semibold tracking-[-0.02em] text-ink">FinIntel</span> : null}
        </Link>
        {!mobile ? (
          <Tooltip content={<span className="inline-flex items-center gap-2">{collapsed ? "Expand sidebar" : "Collapse sidebar"} <Kbd>{shortcutLabel("mod+\\")}</Kbd></span>} side="right">
            <button
              type="button"
              onClick={toggleSidebar}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              data-testid="sidebar-toggle"
              className={cn("ml-auto flex size-7 shrink-0 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-ink/[0.06] hover:text-ink", collapsed && "hidden")}
            >
              <PanelLeftClose aria-hidden className="size-4" />
            </button>
          </Tooltip>
        ) : null}
      </div>

      <nav ref={nav} aria-label="Main" onKeyDown={onKeyDown} className="flex min-h-0 flex-1 flex-col gap-0.5 px-2.5">
        {collapsed ? (
          <Row icon={<PanelLeftOpen aria-hidden />} label="Expand sidebar" collapsed onClick={toggleSidebar} />
        ) : null}
        <Row
          icon={<Search aria-hidden />}
          label="Search"
          collapsed={collapsed}
          onClick={() => palette.open()}
          trailing={<Kbd>{shortcutLabel("mod+k")}</Kbd>}
          testId="sidebar-search"
        />
        <Row icon={<LayoutDashboard aria-hidden />} label="Dashboard" collapsed={collapsed} href="/" active={pathname === "/"} />
        <Row icon={<Plus aria-hidden />} label="New report" collapsed={collapsed} onClick={upload.pick} />

        <p className={cn("eyebrow mt-5 mb-1 px-2.5 transition-opacity", collapsed && "opacity-0")} aria-hidden={collapsed}>
          Reports
        </p>
        <div className="-mx-2.5 min-h-0 flex-1 overflow-y-auto px-2.5 pb-2" data-testid="sidebar-reports">
          {reports.isPending ? (
            Array.from({ length: 4 }, (_, i) => <div key={i} className="mb-0.5 h-8 animate-pulse rounded-lg bg-ink/[0.04]" />)
          ) : reports.isError ? (
            !collapsed ? <p className="px-2.5 py-1.5 text-[0.75rem] text-ink-3">Reports couldn’t be listed.</p> : null
          ) : listed.length === 0 ? (
            !collapsed ? (
              <button type="button" onClick={upload.pick} className="w-full rounded-lg px-2.5 py-1.5 text-left text-[0.78125rem] text-ink-3 hover:bg-ink/[0.04] hover:text-ink-2">
                No reports yet — add one
              </button>
            ) : null
          ) : (
            listed.slice(0, 30).map((r) => <ReportRow key={r.id} report={r} collapsed={collapsed} active={pathname === `/reports/${r.id}`} />)
          )}
        </div>
      </nav>

      <div className="flex shrink-0 flex-col gap-0.5 border-t border-line px-2.5 py-2.5">
        <Row icon={<ShieldCheck aria-hidden />} label="Method & limits" collapsed={collapsed} href="/limitations" active={pathname === "/limitations"} />
        <ThemeSwitch collapsed={collapsed} />
      </div>
    </aside>
  );
}

function Row({
  icon,
  label,
  collapsed,
  href,
  onClick,
  active = false,
  trailing,
  testId,
}: {
  icon: React.ReactNode;
  label: string;
  collapsed: boolean;
  href?: string;
  onClick?: () => void;
  active?: boolean;
  trailing?: React.ReactNode;
  testId?: string;
}) {
  const className = cn(
    "group relative flex h-8 w-full items-center gap-2.5 rounded-lg px-2 text-[0.8125rem] font-medium outline-none transition-colors duration-100",
    "[&>svg]:size-[17px] [&>svg]:shrink-0",
    active ? "bg-ink/[0.07] text-ink" : "text-ink-2 hover:bg-ink/[0.045] hover:text-ink",
    "active:bg-ink/[0.09] active:duration-0", // feedback on pointer-down
  );
  const body = (
    <>
      {icon}
      {!collapsed ? <FadeIn className="min-w-0 flex-1 truncate text-left">{label}</FadeIn> : null}
      {!collapsed && trailing ? <span className="opacity-70 transition-opacity group-hover:opacity-100">{trailing}</span> : null}
    </>
  );
  const el = href ? (
    <Link href={href} className={className} aria-current={active ? "page" : undefined} aria-label={collapsed ? label : undefined} data-nav-row data-testid={testId}>
      {body}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={className} aria-label={collapsed ? label : undefined} data-nav-row data-testid={testId}>
      {body}
    </button>
  );
  return collapsed ? (
    <Tooltip content={label} side="right">
      {el}
    </Tooltip>
  ) : (
    el
  );
}

function ReportRow({ report, collapsed, active }: { report: ReportSummary; collapsed: boolean; active: boolean }) {
  const prefetch = usePrefetchReport();
  const router = useRouter();
  const toast = useToast();
  const [menu, setMenu] = React.useState<{ x: number; y: number } | null>(null);
  const status = statusMeta(report.status);
  const title = reportTitle(report);
  const href = `/reports/${report.id}`;
  const items: MenuItem[] = [
    { label: "Open", hint: "↵", icon: <ExternalLink aria-hidden />, run: () => router.push(href) },
    { label: "Open in a new tab", icon: <ExternalLink aria-hidden />, run: () => window.open(href, "_blank", "noopener") },
    {
      label: "Copy link",
      icon: <Link2 aria-hidden />,
      run: () => {
        void navigator.clipboard?.writeText(new URL(href, window.location.href).href);
        toast({ tone: "ok", title: "Link copied", body: title });
      },
    },
    { label: `Copy report number (${report.id})`, icon: <Copy aria-hidden />, run: () => void navigator.clipboard?.writeText(String(report.id)) },
  ];
  const link = (
    <Link
      href={href}
      data-nav-row
      data-testid="sidebar-report"
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? `${title}, ${status.label}` : undefined}
      onPointerEnter={() => prefetch(report.id)}
      onFocus={() => prefetch(report.id)}
      onContextMenu={(e) => {
        e.preventDefault();
        setMenu({ x: e.clientX, y: e.clientY });
      }}
      className={cn(
        "relative flex h-8 items-center gap-2.5 rounded-lg px-2 text-[0.8125rem] outline-none transition-colors duration-100",
        active ? "bg-ink/[0.07] font-medium text-ink" : "text-ink-2 hover:bg-ink/[0.045] hover:text-ink",
        "active:bg-ink/[0.09] active:duration-0",
      )}
    >
      <span className="relative flex size-[17px] shrink-0 items-center justify-center">
        <span className="flex size-[17px] items-center justify-center rounded-[5px] bg-ink/[0.07] text-[0.59375rem] font-semibold uppercase text-ink-2">
          {title.charAt(0)}
        </span>
        <span aria-hidden className={cn("absolute -bottom-0.5 -right-0.5 size-[7px] rounded-full ring-2 ring-surface-sunk", status.dot, status.spinning && "animate-pulse")} />
      </span>
      {!collapsed ? (
        <>
          <FadeIn className="min-w-0 flex-1 truncate">{title}</FadeIn>
          {report.is_sample ? (
            <FlaskConical aria-label="sample" className="size-3 shrink-0 text-suggested" />
          ) : report.period_label ? (
            <span className="num shrink-0 text-[0.6875rem] text-ink-3">{report.period_label}</span>
          ) : null}
          <span className="sr-only">, {status.label}</span>
        </>
      ) : null}
    </Link>
  );
  return (
    <>
      {collapsed ? (
        <Tooltip content={`${title} · ${status.label}`} side="right">
          {link}
        </Tooltip>
      ) : (
        link
      )}
      <ContextMenu at={menu} items={items} onClose={() => setMenu(null)} />
    </>
  );
}

const THEMES: { value: ThemeChoice; label: string; Icon: typeof Sun }[] = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "Match system", Icon: Monitor },
];

/** Light / Dark / System as a segmented control; a single cycling button on the icon rail. */
function ThemeSwitch({ collapsed }: { collapsed: boolean }) {
  const { theme, setTheme } = useTheme();
  if (collapsed) {
    const i = THEMES.findIndex((t) => t.value === theme);
    const current = THEMES[i]!;
    const next = THEMES[(i + 1) % THEMES.length]!;
    return (
      <Row icon={<current.Icon aria-hidden />} label={`Theme: ${current.label} (switch to ${next.label})`} collapsed onClick={() => setTheme(next.value)} testId="theme-toggle" />
    );
  }
  return (
    <div role="radiogroup" aria-label="Theme" className="mt-1 grid grid-cols-3 gap-0.5 rounded-lg bg-ink/[0.05] p-0.5" data-testid="theme-toggle">
      {THEMES.map(({ value, label, Icon }) => (
        <Tooltip key={value} content={label}>
          <button
            type="button"
            role="radio"
            aria-checked={theme === value}
            aria-label={label}
            onClick={() => setTheme(value)}
            className={cn(
              "relative flex h-7 items-center justify-center rounded-md text-ink-3 transition-colors hover:text-ink",
              theme === value && "text-ink",
            )}
          >
            {theme === value ? (
              <motion.span layoutId="theme-pill" transition={spring.snappy} className="absolute inset-0 rounded-md bg-surface shadow-[var(--shadow-card)]" />
            ) : null}
            <Icon aria-hidden className="relative size-[15px]" />
          </button>
        </Tooltip>
      ))}
    </div>
  );
}

/** Text that appears as the rail widens: a short fade, never a slide. */
function FadeIn({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <motion.span className={className} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.16 }}>
      {children}
    </motion.span>
  );
}

"use client";

import { AnimatePresence, motion } from "motion/react";
import { usePathname } from "next/navigation";
import * as React from "react";
import { useHotkeys } from "@/components/pdf/use-viewer-input";
import { CommandPaletteProvider } from "@/components/shell/command-palette";
import { ShellContext } from "@/components/shell/shell-context";
import { SIDEBAR_NARROW, SIDEBAR_WIDE, Sidebar } from "@/components/shell/sidebar";
import { TopBar } from "@/components/shell/top-bar";
import { project, spring, useSafeMotion } from "@/lib/motion";

const KEY = "finintel-sidebar";

/**
 * The app frame: a fixed sidebar (an icon rail when collapsed, a drawer below 1024 px), the top
 * bar, and the page. The sidebar's width is one CSS variable read by the sidebar and the page,
 * so both change together; the drawer slides on a spring and can be dragged shut.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = React.useState(false);
  const [drawer, setDrawer] = React.useState(false);
  const pathname = usePathname();
  const safe = useSafeMotion(); // reduced motion: these fade instead of moving

  React.useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(KEY) === "collapsed");
    } catch {
      // storage unavailable: expanded
    }
  }, []);
  React.useEffect(() => setDrawer(false), [pathname]);

  const toggleSidebar = React.useCallback(() => {
    if (window.matchMedia("(max-width: 1023px)").matches) return setDrawer((d) => !d);
    setCollapsed((c) => {
      try {
        localStorage.setItem(KEY, c ? "expanded" : "collapsed");
      } catch {
        // not remembered
      }
      return !c;
    });
  }, []);
  useHotkeys(true, [{ combo: "mod+\\", inFields: true, run: toggleSidebar }]);

  const value = React.useMemo(() => ({ collapsed, toggleSidebar, drawer, setDrawer }), [collapsed, toggleSidebar, drawer]);
  return (
    <ShellContext.Provider value={value}>
      <CommandPaletteProvider>
        {/* The sidebar's width is layout, so it changes in one step (only transform and opacity
            animate); its labels fade in (Sidebar). */}
        <div
          className="min-h-dvh"
          style={{ "--sidebar-w": `${collapsed ? SIDEBAR_NARROW : SIDEBAR_WIDE}px` } as React.CSSProperties}
        >
          <a href="#main" className="sr-only z-[100] rounded-lg bg-surface px-3 py-2 focus:not-sr-only focus:fixed focus:left-3 focus:top-3">
            Skip to content
          </a>
          <div className="fixed inset-y-0 left-0 z-50 hidden lg:block">
            <Sidebar />
          </div>
          <AnimatePresence>
            {drawer ? (
              <>
                <motion.div
                  key="scrim"
                  className="fixed inset-0 z-50 bg-[oklch(0.15_0.02_262/0.3)] backdrop-blur-[2px] lg:hidden"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  onClick={() => setDrawer(false)}
                />
                <motion.div
                  key="drawer"
                  className="fixed inset-y-0 left-0 z-50 shadow-[var(--shadow-pop)] lg:hidden"
                  initial={safe({ x: -SIDEBAR_WIDE })}
                  animate={safe({ x: 0 }, 1)}
                  exit={safe({ x: -SIDEBAR_WIDE })}
                  transition={spring.modal}
                  onKeyDown={(e) => e.key === "Escape" && setDrawer(false)}
                  // Drag it shut: 1:1, resists being pulled open further, and closes if the flick
                  // would carry it past half its width.
                  drag="x"
                  dragConstraints={{ left: 0, right: 0 }}
                  dragElastic={{ left: 1, right: 0.06 }}
                  dragSnapToOrigin
                  onDragEnd={(_, info) => {
                    if (info.offset.x + project(info.velocity.x) < -SIDEBAR_WIDE / 2) setDrawer(false);
                  }}
                >
                  <Sidebar mobile />
                </motion.div>
              </>
            ) : null}
          </AnimatePresence>
          <div className="flex min-h-dvh min-w-0 flex-col lg:pl-[var(--sidebar-w)]">
            <TopBar />
            <div id="main" className="flex min-w-0 flex-1 flex-col">
              {children}
            </div>
          </div>
        </div>
      </CommandPaletteProvider>
    </ShellContext.Provider>
  );
}

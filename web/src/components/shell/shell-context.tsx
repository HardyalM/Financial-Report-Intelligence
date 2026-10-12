"use client";

import * as React from "react";

interface Shell {
  collapsed: boolean;
  toggleSidebar: () => void;
  /** Below `lg` the sidebar is a drawer over the page. */
  drawer: boolean;
  setDrawer: (open: boolean) => void;
}

export const ShellContext = React.createContext<Shell>({
  collapsed: false,
  toggleSidebar: () => undefined,
  drawer: false,
  setDrawer: () => undefined,
});

export const useShell = () => React.useContext(ShellContext);

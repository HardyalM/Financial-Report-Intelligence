"use client";

import * as React from "react";

export type ThemeChoice = "light" | "dark" | "system";
const KEY = "finintel-theme";

/**
 * Runs before first paint (inlined in <head>): the saved choice is applied before anything is
 * drawn, so a dark-mode reader never sees a white flash.
 */
export const THEME_BOOT_SCRIPT = `try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

const ThemeContext = React.createContext<{
  theme: ThemeChoice;
  resolved: "light" | "dark";
  setTheme: (t: ThemeChoice) => void;
}>({ theme: "system", resolved: "light", setTheme: () => undefined });

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<ThemeChoice>("system");
  const [systemDark, setSystemDark] = React.useState(false);

  React.useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved === "light" || saved === "dark") setThemeState(saved);
    } catch {
      // storage unavailable: follow the system
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(media.matches);
    const onChange = () => setSystemDark(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const setTheme = React.useCallback((t: ThemeChoice) => {
    setThemeState(t);
    const root = document.documentElement;
    // Colours change in one frame, without every transition in the app animating at once.
    root.classList.add("theme-switching");
    if (t === "system") delete root.dataset.theme;
    else root.dataset.theme = t;
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove("theme-switching")));
    try {
      if (t === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, t);
    } catch {
      // not remembered, still applied
    }
  }, []);

  const resolved = theme === "system" ? (systemDark ? "dark" : "light") : theme;
  const value = React.useMemo(() => ({ theme, resolved, setTheme }), [theme, resolved, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return React.useContext(ThemeContext);
}

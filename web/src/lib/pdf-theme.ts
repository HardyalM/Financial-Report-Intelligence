"use client";

import * as React from "react";

export interface PageTheme {
  bg: [number, number, number];
  fg: [number, number, number];
}

/** A CSS colour (any syntax the browser knows, oklch included) as 0–255 RGB. */
function resolve(cssColor: string): [number, number, number] {
  const c = document.createElement("canvas");
  c.width = c.height = 1;
  const ctx = c.getContext("2d", { willReadFrequently: true })!;
  ctx.fillStyle = "#000";
  ctx.fillStyle = cssColor;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return [r!, g!, b!];
}

function isDark(): boolean {
  const forced = document.documentElement.dataset.theme;
  if (forced === "light") return false;
  if (forced === "dark") return true;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function current(): PageTheme | null {
  if (!isDark()) return null;
  const style = getComputedStyle(document.documentElement);
  return {
    bg: resolve(style.getPropertyValue("--surface").trim() || "#1c1d21"),
    fg: resolve(style.getPropertyValue("--ink").trim() || "#f2f2f0"),
  };
}

/**
 * The page colours for the app's theme: null in light mode (pages as printed), the app's own
 * surface and ink in dark mode. Follows the system setting and `data-theme` as they change.
 */
export function usePageTheme(): PageTheme | null {
  const [theme, setTheme] = React.useState<PageTheme | null>(null);
  React.useEffect(() => {
    const update = () =>
      setTheme((prev) => {
        const next = current();
        return JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
      });
    update();
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", update);
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      media.removeEventListener("change", update);
      observer.disconnect();
    };
  }, []);
  return theme;
}

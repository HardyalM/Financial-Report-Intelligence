"use client";

import * as React from "react";

/** True after `ms` without activity; `poke` marks activity. Drives the auto-hiding toolbar. */
export function useIdle(ms = 2200): [boolean, () => void] {
  const [idle, setIdle] = React.useState(false);
  const timer = React.useRef<number | undefined>(undefined);
  const poke = React.useCallback(() => {
    setIdle(false);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setIdle(true), ms);
  }, [ms]);
  React.useEffect(() => {
    poke();
    return () => window.clearTimeout(timer.current);
  }, [poke]);
  return [idle, poke];
}

export const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** "mod+f" means Cmd+F on a Mac and Ctrl+F elsewhere. */
export function shortcutLabel(combo: string): string {
  return combo
    .split("+")
    .map((k) => (k === "mod" ? (IS_MAC ? "⌘" : "Ctrl") : k === "shift" ? (IS_MAC ? "⇧" : "Shift") : k.length === 1 ? k.toUpperCase() : k))
    .join(IS_MAC ? "" : "+");
}

function matches(e: KeyboardEvent, combo: string): boolean {
  const parts = combo.toLowerCase().split("+");
  const key = parts.pop()!;
  const mod = parts.includes("mod");
  const shift = parts.includes("shift");
  const modDown = IS_MAC ? e.metaKey : e.ctrlKey;
  if (mod !== modDown || (shift && !e.shiftKey)) return false;
  if (!mod && (e.metaKey || e.ctrlKey || e.altKey)) return false;
  const k = e.key.toLowerCase();
  if (key === "=" || key === "plus") return k === "=" || k === "+";
  if (key === "-" || key === "minus") return k === "-" || k === "_";
  return k === key;
}

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

/**
 * Viewer shortcuts while `active` (the reader is open, or the panel viewer has focus or the
 * pointer). Typing in a field keeps its keys, except shortcuts marked `inFields`.
 */
export function useHotkeys(
  active: boolean,
  bindings: { combo: string; run: (e: KeyboardEvent) => void; inFields?: boolean }[],
) {
  const ref = React.useRef(bindings);
  ref.current = bindings;
  React.useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      for (const b of ref.current) {
        if (!matches(e, b.combo)) continue;
        if (typing(e.target) && !b.inFields) continue;
        e.preventDefault();
        e.stopPropagation();
        b.run(e);
        return;
      }
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [active]);
}

export const ZOOM_MIN = 0.5;
export const ZOOM_MAX = 4;
export const clampZoom = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));

/**
 * Pinch to zoom on a scroll container, anchored under the fingers or pointer: trackpad pinch
 * (ctrl+wheel in Chrome and Firefox), Safari's gesture events, and two-finger touch. The scroll
 * position is corrected so the point under the pointer stays put.
 */
export function usePinchZoom(
  scroller: React.RefObject<HTMLElement | null>,
  zoom: number,
  setZoom: (z: number) => void,
) {
  const zoomRef = React.useRef(zoom);
  zoomRef.current = zoom;
  const pendingAnchor = React.useRef<{ x: number; y: number; from: number } | null>(null);

  const zoomAt = React.useCallback(
    (next: number, clientX: number, clientY: number) => {
      const el = scroller.current;
      const from = zoomRef.current;
      const to = clampZoom(next);
      if (!el || to === from) return;
      const box = el.getBoundingClientRect();
      pendingAnchor.current = { x: clientX - box.left, y: clientY - box.top, from };
      zoomRef.current = to;
      setZoom(to);
    },
    [scroller, setZoom],
  );

  // After the new zoom has laid out: keep the anchored point under the pointer.
  React.useLayoutEffect(() => {
    const el = scroller.current;
    const a = pendingAnchor.current;
    if (!el || !a) return;
    pendingAnchor.current = null;
    const ratio = zoom / a.from;
    el.scrollLeft = (el.scrollLeft + a.x) * ratio - a.x;
    el.scrollTop = (el.scrollTop + a.y) * ratio - a.y;
  }, [zoom, scroller]);

  React.useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return; // a trackpad pinch arrives as ctrl+wheel
      e.preventDefault();
      zoomAt(zoomRef.current * Math.exp(-e.deltaY * 0.0105), e.clientX, e.clientY);
    };
    let gestureStart = 1;
    const onGestureStart = (e: Event) => {
      e.preventDefault();
      gestureStart = zoomRef.current;
    };
    const onGestureChange = (e: Event) => {
      e.preventDefault();
      const g = e as Event & { scale: number; clientX: number; clientY: number };
      zoomAt(gestureStart * g.scale, g.clientX, g.clientY);
    };
    const touches = new Map<number, { x: number; y: number }>();
    let pinch: { distance: number; zoom: number } | null = null;
    const spread = () => {
      const [a, b] = [...touches.values()];
      return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
    };
    const onPointerDown = (e: PointerEvent) => {
      if (e.pointerType !== "touch") return;
      touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (touches.size === 2) pinch = { distance: spread(), zoom: zoomRef.current };
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!touches.has(e.pointerId)) return;
      touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch && touches.size === 2 && pinch.distance > 0) {
        const [a, b] = [...touches.values()];
        zoomAt(pinch.zoom * (spread() / pinch.distance), (a!.x + b!.x) / 2, (a!.y + b!.y) / 2);
      }
    };
    const onPointerUp = (e: PointerEvent) => {
      touches.delete(e.pointerId);
      if (touches.size < 2) pinch = null;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("gesturestart", onGestureStart);
    el.addEventListener("gesturechange", onGestureChange);
    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", onPointerUp);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("gesturestart", onGestureStart);
      el.removeEventListener("gesturechange", onGestureChange);
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("pointermove", onPointerMove);
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", onPointerUp);
    };
  }, [scroller, zoomAt]);

  return zoomAt;
}

/**
 * Hand panning with momentum for a mouse: hold Space and drag, or drag with the middle button.
 * (Trackpads and touch already scroll natively with momentum.) Text selection is untouched.
 */
export function useDragPan(scroller: React.RefObject<HTMLElement | null>): boolean {
  const [space, setSpace] = React.useState(false);
  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code === "Space" && !typing(e.target) && scroller.current?.matches(":hover")) {
        e.preventDefault();
        setSpace(true);
      }
    };
    const up = (e: KeyboardEvent) => e.code === "Space" && setSpace(false);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [scroller]);

  React.useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    let drag: { x: number; y: number; t: number; vx: number; vy: number } | null = null;
    let raf = 0;
    const onDown = (e: PointerEvent) => {
      if (e.pointerType !== "mouse" || !(e.button === 1 || (e.button === 0 && space))) return;
      e.preventDefault();
      cancelAnimationFrame(raf);
      el.setPointerCapture(e.pointerId);
      drag = { x: e.clientX, y: e.clientY, t: performance.now(), vx: 0, vy: 0 };
    };
    const onMove = (e: PointerEvent) => {
      if (!drag) return;
      const now = performance.now();
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      const dt = Math.max(1, now - drag.t);
      el.scrollLeft -= dx;
      el.scrollTop -= dy;
      drag = { x: e.clientX, y: e.clientY, t: now, vx: 0.8 * (dx / dt) + 0.2 * drag.vx, vy: 0.8 * (dy / dt) + 0.2 * drag.vy };
    };
    const onUp = () => {
      if (!drag) return;
      let { vx, vy } = drag;
      drag = null;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      let last = performance.now();
      const glide = (now: number) => {
        const dt = now - last;
        last = now;
        el.scrollLeft -= vx * dt;
        el.scrollTop -= vy * dt;
        const decay = Math.pow(0.94, dt / 16);
        vx *= decay;
        vy *= decay;
        if (Math.abs(vx) + Math.abs(vy) > 0.02) raf = requestAnimationFrame(glide);
      };
      raf = requestAnimationFrame(glide);
    };
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
    };
  }, [scroller, space]);
  return space;
}

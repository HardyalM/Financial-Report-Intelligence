"use client";

import { animate } from "motion/react";
import * as React from "react";
import { rubberClamp, spring, VelocityTracker } from "@/lib/motion";

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
  // The zoom the fingers ask for, before the rubber band (a gesture's own coordinate).
  const intent = React.useRef<number | null>(null);
  const settle = React.useRef<{ stop: () => void } | null>(null);
  const lastPoint = React.useRef({ x: 0, y: 0 });

  const apply = React.useCallback(
    (to: number, clientX: number, clientY: number) => {
      const el = scroller.current;
      const from = zoomRef.current;
      if (!el || to === from) return;
      const box = el.getBoundingClientRect();
      pendingAnchor.current = { x: clientX - box.left, y: clientY - box.top, from };
      zoomRef.current = to;
      setZoom(to);
    },
    [scroller, setZoom],
  );

  /** A zoom from a button or key: always within the limits. */
  const zoomAt = React.useCallback(
    (next: number, clientX: number, clientY: number) => {
      settle.current?.stop();
      intent.current = null;
      apply(clampZoom(next), clientX, clientY);
    },
    [apply],
  );

  /** A zoom from a pinch: past a limit it gives with growing resistance instead of stopping. */
  const pinchTo = React.useCallback(
    (next: number, clientX: number, clientY: number) => {
      settle.current?.stop();
      lastPoint.current = { x: clientX, y: clientY };
      intent.current = next;
      apply(rubberClamp(next, ZOOM_MIN, ZOOM_MAX, ZOOM_MAX - ZOOM_MIN), clientX, clientY);
    },
    [apply],
  );

  /** The pinch ended: a zoom left past a limit springs back to it, from where it is. */
  const release = React.useCallback(() => {
    intent.current = null;
    const from = zoomRef.current;
    const to = clampZoom(from);
    if (to === from) return;
    const { x, y } = lastPoint.current;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return apply(to, x, y);
    settle.current = animate(from, to, { ...spring.snappy, onUpdate: (z) => apply(z, x, y) });
  }, [apply]);

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
    let wheelEnd = 0;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return; // a trackpad pinch arrives as ctrl+wheel
      e.preventDefault();
      pinchTo((intent.current ?? zoomRef.current) * Math.exp(-e.deltaY * 0.0105), e.clientX, e.clientY);
      // A pinch has no "end" event as wheel input: it has ended when the events stop.
      window.clearTimeout(wheelEnd);
      wheelEnd = window.setTimeout(release, 90);
    };
    let gestureStart = 1;
    const onGestureStart = (e: Event) => {
      e.preventDefault();
      gestureStart = zoomRef.current;
    };
    const onGestureChange = (e: Event) => {
      e.preventDefault();
      const g = e as Event & { scale: number; clientX: number; clientY: number };
      pinchTo(gestureStart * g.scale, g.clientX, g.clientY);
    };
    const onGestureEnd = (e: Event) => {
      e.preventDefault();
      release();
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
        pinchTo(pinch.zoom * (spread() / pinch.distance), (a!.x + b!.x) / 2, (a!.y + b!.y) / 2);
      }
    };
    const onPointerUp = (e: PointerEvent) => {
      touches.delete(e.pointerId);
      if (touches.size < 2 && pinch) {
        pinch = null;
        release();
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("gesturestart", onGestureStart);
    el.addEventListener("gesturechange", onGestureChange);
    el.addEventListener("gestureend", onGestureEnd);
    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", onPointerUp);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("gesturestart", onGestureStart);
      el.removeEventListener("gesturechange", onGestureChange);
      el.removeEventListener("gestureend", onGestureEnd);
      window.clearTimeout(wheelEnd);
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("pointermove", onPointerMove);
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", onPointerUp);
    };
  }, [scroller, pinchTo, release]);

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
    let drag: { x: number; y: number } | null = null;
    const tracker = new VelocityTracker();
    let raf = 0;
    const stopGlide = () => cancelAnimationFrame(raf);
    const onDown = (e: PointerEvent) => {
      stopGlide(); // a touch mid-glide catches the page where it is
      if (e.pointerType !== "mouse" || !(e.button === 1 || (e.button === 0 && space))) return;
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      drag = { x: e.clientX, y: e.clientY };
      tracker.reset();
      tracker.push(e.clientX, e.clientY);
    };
    const onMove = (e: PointerEvent) => {
      if (!drag) return;
      // 1:1 with the pointer, from where it was grabbed.
      el.scrollLeft -= e.clientX - drag.x;
      el.scrollTop -= e.clientY - drag.y;
      drag = { x: e.clientX, y: e.clientY };
      tracker.push(e.clientX, e.clientY);
    };
    const onUp = () => {
      if (!drag) return;
      drag = null;
      const v = tracker.velocity(); // px/s
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      // Glide on with Apple's scroll deceleration (0.998 per ms): it comes to rest exactly where
      // project() says a flick of this speed lands.
      let vx = v.x / 1000;
      let vy = v.y / 1000;
      let last = performance.now();
      const glide = (now: number) => {
        const dt = now - last;
        last = now;
        el.scrollLeft -= vx * dt;
        el.scrollTop -= vy * dt;
        const decay = Math.pow(0.998, dt);
        vx *= decay;
        vy *= decay;
        if (Math.abs(vx) + Math.abs(vy) > 0.01) raf = requestAnimationFrame(glide);
      };
      raf = requestAnimationFrame(glide);
    };
    el.addEventListener("wheel", stopGlide, { passive: true });
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
    return () => {
      stopGlide();
      el.removeEventListener("wheel", stopGlide);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
    };
  }, [scroller, space]);
  return space;
}

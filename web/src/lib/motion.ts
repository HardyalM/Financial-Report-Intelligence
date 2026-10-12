"use client";

/**
 * Motion foundations (apple-design skill). Every animation in the app uses one of these springs,
 * so movement has one character:
 *
 * - critically damped by default (bounce 0 = damping ratio 1.0): no overshoot, settles calmly;
 * - `momentum` (bounce 0.2 ≈ damping 0.8) only after a flick or a drag release, where overshoot
 *   reads as the object carrying the energy you gave it.
 *
 * `duration` here is Apple's "response" (time to reach the target), not a fixed length: a spring
 * started mid-flight re-targets from the current on-screen value and velocity.
 *
 * Reduced motion is honoured globally (MotionConfig reducedMotion="user"): transforms become
 * instant and only opacity animates, a cross-fade.
 */
import * as React from "react";

export const spring = {
  /** Menus, toasts, presses, small surfaces. */
  snappy: { type: "spring", bounce: 0, duration: 0.28 },
  /** Modals, the command palette, sheets and drawers. */
  modal: { type: "spring", bounce: 0, duration: 0.35 },
  /** Page transitions, the sidebar, layout changes. */
  page: { type: "spring", bounce: 0, duration: 0.4 },
  /** Only after a gesture carried momentum (a flick, a drag release). */
  momentum: { type: "spring", bounce: 0.2, duration: 0.4 },
} as const;

/**
 * Where a flick will come to rest: Apple's exponential-decay projection (Designing Fluid
 * Interfaces). `velocity` in px/s; `rate` 0.998 is normal scroll feel, 0.99 snappier.
 */
export function project(velocity: number, rate = 0.998): number {
  return ((velocity / 1000) * rate) / (1 - rate);
}

/**
 * Rubber-band past a boundary: the further past it, the less the content follows. `overshoot` is
 * how far past the bound the input is, `dimension` the size of the thing being moved.
 */
export function rubberband(overshoot: number, dimension: number, constant = 0.55): number {
  if (dimension <= 0) return 0;
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot));
}

/** A value held inside [min, max], rubber-banded beyond it. */
export function rubberClamp(value: number, min: number, max: number, dimension: number): number {
  if (value < min) return min - rubberband(min - value, dimension);
  if (value > max) return max + rubberband(value - max, dimension);
  return value;
}

/**
 * Release velocity from the last few pointer samples (px/s). Recent samples only: a pause before
 * letting go means no throw.
 */
export class VelocityTracker {
  private samples: { t: number; x: number; y: number }[] = [];
  push(x: number, y: number, t = performance.now()) {
    this.samples.push({ t, x, y });
    while (this.samples.length > 6 || (this.samples.length > 1 && t - this.samples[0]!.t > 100)) this.samples.shift();
  }
  reset() {
    this.samples = [];
  }
  velocity(now = performance.now()): { x: number; y: number } {
    const first = this.samples[0];
    const last = this.samples.at(-1);
    if (!first || !last || last === first || now - last.t > 80) return { x: 0, y: 0 };
    const dt = (last.t - first.t) / 1000;
    return dt > 0 ? { x: (last.x - first.x) / dt, y: (last.y - first.y) / dt } : { x: 0, y: 0 };
  }
}

const REDUCE = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void) {
  const media = window.matchMedia(REDUCE);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/**
 * The user's reduced-motion setting, live. Server render and hydration use `false` (so the markup
 * matches); anything mounted in the browser afterwards reads the real setting on its first render.
 */
export function usePrefersReducedMotion(): boolean {
  return React.useSyncExternalStore(
    subscribe,
    () => window.matchMedia(REDUCE).matches,
    () => false,
  );
}

type Values = Record<string, string | number>;

/**
 * Motion values made safe for reduced motion: with the setting on, every value but opacity is
 * dropped, so a surface cross-fades instead of moving. (Motion's own reduced-motion mode skips the
 * animation but still draws the start state for a frame, which is a jump.) `rest` is the opacity
 * to use when `values` has none: 0 for initial/exit states, 1 for animate targets.
 */
export function useSafeMotion(): (values: Values, rest?: 0 | 1) => Values {
  const reduce = usePrefersReducedMotion();
  return React.useCallback(
    (values: Values, rest: 0 | 1 = 0) => (reduce ? { opacity: values.opacity ?? rest } : values),
    [reduce],
  );
}

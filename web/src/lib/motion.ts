/**
 * Motion tokens: every animation in the app uses one of these springs, so movement has one
 * character. Reduced motion is honoured globally (MotionConfig reducedMotion="user").
 */
export const spring = {
  /** Menus, toasts, hovers: quick, no visible overshoot. */
  snappy: { type: "spring", stiffness: 520, damping: 38, mass: 0.7 },
  /** Modals and the command palette: a touch softer. */
  modal: { type: "spring", stiffness: 420, damping: 34, mass: 0.8 },
  /** Page transitions and layout changes. */
  page: { type: "spring", stiffness: 300, damping: 32, mass: 0.9 },
} as const;

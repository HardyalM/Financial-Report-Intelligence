"use client";

import { X } from "lucide-react";

/** Clears the selection: the "click off" for the evidence panel (Esc does the same). */
export function CloseButton({ onClose }: { onClose: () => void }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close source"
      data-testid="evidence-close"
      className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-sunk hover:text-ink"
    >
      <X aria-hidden className="size-4" />
    </button>
  );
}

"use client";

import {
  Ban,
  Bot,
  CircleAlert,
  Lock,
  SearchX,
  Shield,
  ShieldCheck,
  Sigma,
  TriangleAlert,
  UserCheck,
} from "lucide-react";
import * as React from "react";
import { Badge, type Tone } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { ROW_STATE_LABEL, type RowState } from "@/lib/states";

export const ROW_TONE: Record<RowState, Tone> = {
  R1: "ok",
  R2: "single",
  R3: "derived",
  R4: "confirmed",
  R5: "amber",
  R6: "review",
  R7: "suggested",
  R8: "missing",
  R9: "muted",
  R10: "muted",
};

const ROW_ICON: Record<RowState, React.ComponentType<{ "aria-hidden"?: boolean }>> = {
  R1: ShieldCheck,
  R2: Shield,
  R3: Sigma,
  R4: UserCheck,
  R5: TriangleAlert,
  R6: CircleAlert,
  R7: Bot,
  R8: SearchX,
  R9: Ban,
  R10: Lock,
};

export function StateBadge({
  state,
  label,
  title,
  className,
}: {
  state: RowState;
  label?: string;
  title?: React.ReactNode;
  className?: string;
}) {
  const Icon = ROW_ICON[state];
  const badge = (
    <Badge tone={ROW_TONE[state]} className={className} tabIndex={title ? 0 : undefined}>
      <Icon aria-hidden />
      {label ?? ROW_STATE_LABEL[state]}
    </Badge>
  );
  return title ? <Tooltip content={title}>{badge}</Tooltip> : badge;
}

/** A page reference. Enter or click opens the evidence (UI.md section 10: every chip is focusable). */
export function PageChip({
  page,
  label,
  onOpen,
  testId = "page-chip",
}: {
  page: number;
  label?: string | null;
  onOpen?: () => void;
  testId?: string;
}) {
  const folio = label && label !== String(page) ? ` · printed p. ${label}` : "";
  return (
    <Tooltip content={`PDF p. ${page}${folio}`}>
      <button
        type="button"
        data-testid={testId}
        onClick={onOpen}
        className={cn(
          "num inline-flex h-5 items-center rounded border border-line bg-surface px-1.5 font-mono text-[11px] text-ink-2",
          "transition-colors hover:border-accent hover:text-accent",
        )}
        aria-label={`Open PDF page ${page}${label ? `, printed page ${label}` : ""}`}
      >
        p.{page}
      </button>
    </Tooltip>
  );
}

export function NoteChip({ note }: { note: string }) {
  return (
    <Tooltip content="Note reference printed beside the line">
      <span
        tabIndex={0}
        data-testid="note-chip"
        className="num inline-flex h-5 items-center rounded border border-dashed border-line-strong px-1.5 text-[11px] text-ink-3"
      >
        Note {note}
      </span>
    </Tooltip>
  );
}

export function CodeHint({ code }: { code: string }) {
  return <span className="font-mono text-[11px] text-ink-3">{code}</span>;
}

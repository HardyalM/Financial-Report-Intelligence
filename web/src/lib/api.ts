"use client";

/**
 * The API client (/api/* is forwarded to finintel serve). Client-side on purpose: Playwright can
 * serve fixtures by intercepting these calls, or run them against the real API.
 */
import * as React from "react";
import { useReportQuery } from "@/lib/queries";
import type { CommentaryResponse, Report, ReportedMetrics, Review } from "@/lib/types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { accept: "application/json", ...(init.headers ?? {}) },
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "unreachable", "The API can’t be reached.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: { code?: string; message?: string } | { msg?: string }[];
    } | null;
    const detail = body?.detail;
    if (Array.isArray(detail)) {
      throw new ApiError(response.status, "invalid_request", detail.map((d) => d.msg).join("; "));
    }
    throw new ApiError(
      response.status,
      detail?.code ?? `http_${response.status}`,
      detail?.message ?? response.statusText,
    );
  }
  if (response.status === 204) return null as T; // no content (a delete)
  return (await response.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ------------------------------------------------------------------------------- decisions

export interface UploadResult {
  id: number;
  sha256: string;
  status: string;
  duplicate: boolean;
}

export function uploadPdf(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<UploadResult>("/uploads", { method: "POST", body: form });
}

export interface OverrideBody {
  action: "accept_candidate" | "set_value" | "set_null";
  item: string;
  period_id: string;
  candidate_id?: string;
  value?: number;
  raw_text?: string;
  page?: number;
  reason?: string;
  force?: boolean;
}

export interface OverrideResult {
  override_id: number;
  anchored: boolean;
  pack_version: number;
  pack_sha: string;
  stale: boolean;
  warning_codes: string[];
}

export interface StatusResult {
  id: number;
  status: string;
  reran: string[];
}

export const decisions = {
  override: (id: number, body: OverrideBody) => post<OverrideResult>(`/reports/${id}/overrides`, body),
  unit: (id: number, body: { currency: string; unit_scale: number; evidence_page: number }) =>
    post<StatusResult>(`/reports/${id}/unit-confirmation`, body),
  statementLocation: (id: number, body: { statement_type: string; page: number }) =>
    post<StatusResult>(`/reports/${id}/statement-location`, body),
  documentType: (id: number, body: { document_type: string; reason: string }) =>
    post<StatusResult>(`/reports/${id}/document-type`, body),
};

// ------------------------------------------------------------------------------- reading

export interface ReportData {
  report: Report;
  commentary: CommentaryResponse | null;
  /** Why there is no commentary to show, when the API said (e.g. it is in an older format). */
  commentaryNote: string | null;
  review: Review | null;
  /** A bank's own CET1 ratio and NIM, as stated in its narrative (empty for others). */
  reported: ReportedMetrics;
}

export type Loadable =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: ReportData };

/** A report is still moving while the worker has queued or running stages for it. */
export function inProgress(report: Report): boolean {
  return report.status === "queued" || report.status === "processing";
}

export async function fetchReport(id: string): Promise<ReportData> {
  const path = `/reports/${encodeURIComponent(id)}`;
  const report = await request<Report>(path);
  const empty: ReportedMetrics = { metrics: [], notes: [] };
  let commentaryNote: string | null = null;
  const [commentary, review, reported] = await Promise.all([
    request<CommentaryResponse>(`${path}/commentary`).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) {
        if (e.code === "commentary_outdated") commentaryNote = e.message;
        return null;
      }
      throw e;
    }),
    request<Review>(`${path}/review`).catch(() => null),
    report.document_type === "bank"
      ? request<ReportedMetrics>(`${path}/reported-metrics`).catch(() => empty)
      : Promise.resolve(empty),
  ]);
  return { report, commentary, commentaryNote, review, reported };
}

/**
 * The report, its commentary and its review queue, from the query cache (lib/queries.ts): a
 * report seen or hovered before appears at once; while stages run it polls every `pollMs`
 * (UI.md section 3). `reload` re-reads after a person's decision.
 */
export function useReport(id: string, pollMs = 1000): { state: Loadable; reload: () => Promise<void> } {
  const q = useReportQuery(id, pollMs);
  const reload = React.useCallback(async () => {
    await q.refetch();
  }, [q]);
  // A failed refresh keeps what is on screen; only a failed first load shows the error.
  const state: Loadable = q.data
    ? { status: "ready", data: q.data }
    : q.error
      ? {
          status: "error",
          error: q.error instanceof ApiError ? q.error : new ApiError(0, "unknown", String(q.error)),
        }
      : { status: "loading" };
  return { state, reload };
}

"use client";

/**
 * Reads the report, its commentary and its review queue from the API (/api/* is forwarded to
 * finintel serve). Client-side on purpose: Playwright serves fixtures by intercepting these calls.
 */
import { useEffect, useState } from "react";
import type { CommentaryResponse, Report, Review } from "@/lib/types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { signal, headers: { accept: "application/json" } });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "unreachable", "The API can’t be reached.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: { code?: string; message?: string } } | null;
    throw new ApiError(
      response.status,
      body?.detail?.code ?? `http_${response.status}`,
      body?.detail?.message ?? response.statusText,
    );
  }
  return (await response.json()) as T;
}

export interface ReportData {
  report: Report;
  commentary: CommentaryResponse | null;
  review: Review | null;
}

export type Loadable =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: ReportData };

export function useReport(id: string): Loadable {
  const [state, setState] = useState<Loadable>({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    setState({ status: "loading" });
    (async () => {
      try {
        const report = await getJson<Report>(`/reports/${encodeURIComponent(id)}`, signal);
        const [commentary, review] = await Promise.all([
          getJson<CommentaryResponse>(`/reports/${encodeURIComponent(id)}/commentary`, signal).catch((e: unknown) => {
            if (e instanceof ApiError && e.status === 404) return null;
            throw e;
          }),
          getJson<Review>(`/reports/${encodeURIComponent(id)}/review`, signal).catch(() => null),
        ]);
        setState({ status: "ready", data: { report, commentary, review } });
      } catch (error) {
        if ((error as Error).name === "AbortError") return;
        setState({
          status: "error",
          error: error instanceof ApiError ? error : new ApiError(0, "unknown", String(error)),
        });
      }
    })();
    return () => controller.abort();
  }, [id]);
  return state;
}

"use client";

/**
 * The data layer: TanStack Query over the API client. Reports and the report list are cached, so
 * a report opened before (or hovered, which prefetches it) appears at once and is refreshed in
 * the background. While a report's stages run it polls (UI.md section 3).
 *
 * Optimistic updates are limited to status and workflow, never figures: a decision shows as
 * "Processing" before the server answers; every number on screen is still the server's.
 */
import { QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { ApiError, fetchReport, inProgress, type ReportData, request } from "@/lib/api";
import type { components } from "@/types/generated/api";

export type ReportSummary = components["schemas"]["ReportSummary"];

export const keys = {
  reports: ["reports"] as const,
  report: (id: string | number) => ["report", String(id)] as const,
};

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        gcTime: 10 * 60_000,
        refetchOnWindowFocus: true,
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      },
    },
  });
}

export function useReports() {
  return useQuery({
    queryKey: keys.reports,
    queryFn: () => request<ReportSummary[]>("/reports"),
    // Keep the list fresh while anything in it is still being read.
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "queued" || r.status === "processing") ? 2000 : false),
  });
}

const reportQuery = (id: string, pollMs = 1000) => ({
  queryKey: keys.report(id),
  queryFn: () => fetchReport(id),
  refetchInterval: (q: { state: { data?: ReportData } }) =>
    q.state.data && inProgress(q.state.data.report) ? pollMs : (false as const),
});

export function useReportQuery(id: string, pollMs = 1000) {
  return useQuery(reportQuery(id, pollMs));
}

/** Hover or focus on a link to a report: fetch it now, so opening it is instant. */
export function usePrefetchReport() {
  const client = useQueryClient();
  return React.useCallback(
    (id: string | number) => void client.prefetchQuery({ ...reportQuery(String(id)), staleTime: 30_000 }),
    [client],
  );
}

type Patch = (data: ReportData) => ReportData;

/**
 * A person's decision: the optimistic `patch` (status and workflow only) is shown at once; the
 * server's answer replaces it; an error puts back what was there and is thrown to the caller.
 */
export function useDecision(id: string | number) {
  const client = useQueryClient();
  const key = keys.report(id);
  const mutation = useMutation({
    mutationFn: async ({ run }: { run: () => Promise<unknown>; patch?: Patch }) => run(),
    onMutate: async ({ patch }) => {
      await client.cancelQueries({ queryKey: key });
      const before = client.getQueryData<ReportData>(key);
      if (before && patch) client.setQueryData<ReportData>(key, patch(before));
      return { before };
    },
    onError: (_e, _v, context) => {
      if (context?.before) client.setQueryData(key, context.before);
    },
    onSettled: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: key }), client.invalidateQueries({ queryKey: keys.reports })]);
    },
  });
  return React.useCallback(
    (run: () => Promise<unknown>, patch?: Patch) => mutation.mutateAsync({ run, patch }),
    [mutation],
  );
}

/** Optimistic patch: the report is being processed again (a decision that re-runs stages). */
export const markProcessing =
  (extra: Partial<ReportData["report"]> = {}): Patch =>
  (d) => ({ ...d, report: { ...d.report, ...extra, status: "processing" } });

/** After an upload: the new report is in the list at once, before the list is fetched again. */
export function useAddUploaded() {
  const client = useQueryClient();
  return React.useCallback(
    (row: Pick<ReportSummary, "id" | "filename" | "status" | "page_count">) => {
      client.setQueryData<ReportSummary[]>(keys.reports, (list = []) =>
        list.some((r) => r.id === row.id)
          ? list
          : [
              {
                company_name: null, document_type: "other", created_at: new Date().toISOString(),
                period_label: null, currency: null, unit_scale: null, open_review_items: 0, stale: false,
                ...row,
              },
              ...list,
            ],
      );
      void client.invalidateQueries({ queryKey: keys.reports });
    },
    [client],
  );
}

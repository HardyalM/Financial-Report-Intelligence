"use client";

import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { useConfirm } from "@/components/ui/confirm";
import { useToast } from "@/components/ui/toast";
import { useDeleteReport } from "@/lib/queries";

/**
 * Delete a report, the same way from every place that offers it (dashboard, sidebar, report page,
 * command palette): confirm (it cannot be undone), leave the report if it is open, remove it at
 * once, and say what happened, or why not.
 */
export function useDeleteReportAction() {
  const confirm = useConfirm();
  const toast = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const names = React.useRef(new Map<number, string>());
  const del = useDeleteReport({
    deleted: (id) => toast({ tone: "ok", title: "Report deleted", body: names.current.get(id) }),
    failed: (e) => toast({ tone: "error", title: "The report wasn’t deleted", body: e.message }),
  });
  return React.useCallback(
    async (report: { id: number; title: string }) => {
      const ok = await confirm({
        title: `Delete “${report.title}”?`,
        body: (
          <>
            The report is removed for good: its figures, ratios, commentary, the review decisions made on it, and the
            uploaded PDF. This can’t be undone. You can upload the PDF again to read it afresh.
          </>
        ),
        confirmLabel: "Delete report",
        tone: "destructive",
      });
      if (!ok) return;
      names.current.set(report.id, report.title);
      if (pathname === `/reports/${report.id}`) router.push("/");
      del.mutate(report.id);
    },
    [confirm, del, pathname, router],
  );
}

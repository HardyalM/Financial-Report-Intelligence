"use client";

import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Button } from "@/components/ui/button";

export function OpenReport() {
  const router = useRouter();
  const [id, setId] = React.useState("");
  return (
    <form
      className="flex gap-2 rounded-xl border border-line bg-surface p-2 shadow-[var(--shadow-card)]"
      onSubmit={(e) => {
        e.preventDefault();
        if (/^\d+$/.test(id.trim())) router.push(`/reports/${id.trim()}`);
      }}
    >
      <label htmlFor="report-id" className="sr-only">
        Report number
      </label>
      <input
        id="report-id"
        inputMode="numeric"
        autoComplete="off"
        placeholder="Report number, e.g. 1"
        value={id}
        onChange={(e) => setId(e.target.value)}
        className="num h-9 flex-1 rounded-md bg-transparent px-2 text-sm outline-none placeholder:text-ink-3"
      />
      <Button type="submit" disabled={!/^\d+$/.test(id.trim())}>
        Open report <ArrowRight aria-hidden />
      </Button>
    </form>
  );
}

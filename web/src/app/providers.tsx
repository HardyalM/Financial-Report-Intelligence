"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import * as React from "react";
import { AppShell } from "@/components/shell/app-shell";
import { ThemeProvider } from "@/components/shell/theme";
import { UploadProvider } from "@/components/shell/upload";
import { ConfirmProvider } from "@/components/ui/confirm";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeQueryClient } from "@/lib/queries";

/** Everything the app shares: the query cache, theme, motion, notices, uploads and the shell. */
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <MotionConfig reducedMotion="user">
          <ToastProvider>
            <TooltipProvider delayDuration={300} skipDelayDuration={120}>
              <ConfirmProvider>
                <UploadProvider>
                  <AppShell>{children}</AppShell>
                </UploadProvider>
              </ConfirmProvider>
            </TooltipProvider>
          </ToastProvider>
        </MotionConfig>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

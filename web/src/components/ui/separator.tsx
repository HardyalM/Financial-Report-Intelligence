import { cn } from "@/lib/cn";

export function Separator({ className, vertical = false }: { className?: string; vertical?: boolean }) {
  return (
    <div
      role="separator"
      aria-orientation={vertical ? "vertical" : "horizontal"}
      className={cn("shrink-0 bg-line", vertical ? "h-4 w-px" : "h-px w-full", className)}
    />
  );
}

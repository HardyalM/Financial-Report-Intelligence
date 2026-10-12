"use client";

import { motion } from "motion/react";
import { spring, useSafeMotion } from "@/lib/motion";

/** A new page eases in: a short fade and a 6 px rise on the page spring (reduced motion: none). */
export default function Template({ children }: { children: React.ReactNode }) {
  const safe = useSafeMotion(); // reduced motion: these fade instead of moving
  return (
    <motion.div
      className="flex min-w-0 flex-1 flex-col"
      initial={safe({ opacity: 0, y: 6 })}
      animate={safe({ opacity: 1, y: 0 })}
      transition={spring.page}
    >
      {children}
    </motion.div>
  );
}

"use client";

import { motion } from "motion/react";
import { spring } from "@/lib/motion";

/** A new page eases in: a short fade and a 6 px rise on the page spring (reduced motion: none). */
export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      className="flex min-w-0 flex-1 flex-col"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring.page}
    >
      {children}
    </motion.div>
  );
}

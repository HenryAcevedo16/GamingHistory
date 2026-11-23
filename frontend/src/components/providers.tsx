"use client";

import type { ReactNode } from "react";
import { MotionConfig } from "framer-motion";

import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider delay={200}>{children}</TooltipProvider>
    </MotionConfig>
  );
}

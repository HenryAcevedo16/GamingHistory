"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

export const field = "min-w-0 rounded-lg border border-white/15 bg-background/70 px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50";
export const panel = "glass-panel min-w-0 space-y-4 rounded-2xl border border-white/10 bg-card/65 p-4 sm:p-5";
export const message = (error: unknown) => error instanceof Error ? error.message : "Ocurrió un error inesperado.";

export function StudioPage({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return <motion.div initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
    transition={{ duration: reduced ? 0 : 0.22 }} className="mx-auto max-w-[1550px] space-y-6 px-4 py-6 sm:px-8 sm:py-9">{children}</motion.div>;
}

export function Problem({ children }: { children: ReactNode }) {
  return <p role="alert" className="break-words rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-foreground">{children}</p>;
}

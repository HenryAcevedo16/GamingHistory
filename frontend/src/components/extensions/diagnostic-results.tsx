import { Loader2, Terminal } from "lucide-react";

import { CHECK_META, formatDateTime } from "@/components/extensions/plugin-meta";
import type { DiagnosticResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

export function DiagnosticResults({
  report,
  running,
  emptyLabel = "Sin diagnóstico ejecutado en esta sesión.",
}: {
  report?: DiagnosticResponse | null;
  running?: boolean;
  emptyLabel?: string;
}) {
  if (running) {
    return (
      <div className="flex items-center gap-2.5 rounded-xl border border-white/8 bg-white/[0.025] px-3.5 py-3 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
        Ejecutando comprobaciones reales en este equipo…
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex items-start gap-2.5 rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-3.5 py-3">
        <Terminal className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
      </div>
    );
  }

  const { summary } = report;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium",
            report.ok
              ? "border-success/25 bg-success/10 text-success"
              : "border-destructive/30 bg-destructive/10 text-destructive",
          )}
        >
          <span className={cn("status-dot", report.ok ? "bg-success" : "bg-destructive")} />
          {report.ok ? "Diagnóstico correcto" : "Diagnóstico con fallos"}
        </span>
        <span className="font-mono text-[0.68rem] text-muted-foreground">
          {summary.passed} ok / {summary.failed} fallos / {summary.warnings} avisos /{" "}
          {summary.skipped} omitidas · {report.duration_ms} ms
        </span>
      </div>

      <p className="font-mono text-[0.65rem] text-muted-foreground/80">
        Ejecutado {formatDateTime(report.ran_at)}
      </p>

      <ul className="space-y-2">
        {report.checks.map((check) => {
          const meta = CHECK_META[check.status];
          const Icon = meta.icon;
          return (
            <li
              key={check.id}
              className="rounded-xl border border-white/7 bg-white/[0.02] px-3.5 py-2.5"
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Icon className={cn("size-4 shrink-0", meta.className)} aria-hidden />
                <span className="text-sm font-medium">{check.label}</span>
                <span className="rounded border border-white/8 px-1.5 py-0.5 font-mono text-[0.58rem] text-muted-foreground">
                  {check.kind}
                </span>
                {check.optional && (
                  <span className="rounded border border-white/8 px-1.5 py-0.5 font-mono text-[0.58rem] text-muted-foreground">
                    opcional
                  </span>
                )}
                {check.version && (
                  <span className="rounded border border-primary/20 bg-primary/8 px-1.5 py-0.5 font-mono text-[0.58rem] text-primary">
                    v{check.version}
                  </span>
                )}
                <span className="ml-auto font-mono text-[0.6rem] text-muted-foreground/70">
                  {check.duration_ms} ms
                </span>
              </div>
              <p
                className={cn(
                  "mt-1.5 break-words font-mono text-[0.66rem] leading-relaxed",
                  check.status === "fail" ? "text-destructive/90" : "text-muted-foreground",
                )}
              >
                {check.evidence}
              </p>
              {check.hint && (check.status === "fail" || check.status === "warn") && (
                <p className="mt-1.5 rounded-lg bg-warning/8 px-2 py-1.5 text-[0.7rem] leading-snug text-warning/90">
                  {check.hint}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

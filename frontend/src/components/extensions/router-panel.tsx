"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Cloud,
  Loader2,
  RefreshCw,
  Route,
  ShieldAlert,
  Waypoints,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import type { RouterDecision, RouterDecisionsResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

function CapabilityChip({ id }: { id: string }) {
  return (
    <span className="inline-flex h-5 items-center rounded-full border border-white/8 bg-white/[0.03] px-2 font-mono text-[0.58rem] text-muted-foreground">
      {id}
    </span>
  );
}

function DecisionCard({ decision }: { decision: RouterDecision }) {
  const selected = decision.selected;
  return (
    <article className="glass-panel flex flex-col rounded-2xl p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="mono-label">{decision.operation}</p>
          <h3 className="mt-1 font-display text-base font-semibold">{decision.label}</h3>
          <p className="mt-0.5 text-[0.72rem] leading-snug text-muted-foreground">
            {decision.description}
          </p>
        </div>
        {selected ? (
          <span className="inline-flex h-5.5 shrink-0 items-center gap-1.5 rounded-full border border-success/25 bg-success/12 px-2 text-[0.68rem] font-medium text-success">
            <span className="status-dot bg-success" />
            Elegido
          </span>
        ) : (
          <span className="inline-flex h-5.5 shrink-0 items-center gap-1.5 rounded-full border border-warning/25 bg-warning/12 px-2 text-[0.68rem] font-medium text-warning">
            <span className="status-dot bg-warning" />
            Sin editor
          </span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {decision.required_capabilities.map((capability) => (
          <CapabilityChip key={capability} id={capability} />
        ))}
      </div>

      <div className="mt-3 rounded-xl border border-white/7 bg-white/[0.02] px-3 py-2.5">
        {selected ? (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[0.84rem] font-medium">{selected.name}</span>
            <span className="font-mono text-[0.6rem] text-muted-foreground">
              {selected.plugin_id}
            </span>
            <span
              className={cn(
                "ml-auto inline-flex h-5 items-center rounded-full border px-2 text-[0.58rem] font-medium",
                selected.executable
                  ? "border-success/25 bg-success/10 text-success"
                  : "border-warning/25 bg-warning/10 text-warning",
              )}
            >
              {selected.executable ? "ejecutable" : "sin adaptador · Fase 3"}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-warning">
            <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
            <span className="text-[0.78rem] font-medium">Ningún plugin válido ahora mismo</span>
          </div>
        )}
        <p className="mt-1.5 text-[0.7rem] leading-relaxed text-muted-foreground">
          {decision.explanation}
        </p>
      </div>

      <div className="mt-3 border-t border-white/6 pt-2.5">
        <p className="mono-label">Descartados ({decision.discarded.length})</p>
        {decision.discarded.length === 0 ? (
          <p className="mt-1 text-[0.68rem] text-muted-foreground/70">
            No se descartó ningún plugin.
          </p>
        ) : (
          <ul className="mt-1.5 space-y-1">
            {decision.discarded.map((candidate) => (
              <li key={candidate.plugin_id} className="flex items-start gap-2">
                <span
                  className={cn(
                    "status-dot mt-1.5 shrink-0",
                    candidate.eligible ? "bg-info" : "bg-destructive/70",
                  )}
                />
                <div className="min-w-0">
                  <span className="text-[0.7rem] font-medium">{candidate.name}</span>
                  <p className="text-[0.64rem] leading-snug text-muted-foreground">
                    {candidate.reason}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}

function RouterSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {Array.from({ length: 4 }).map((_, index) => (
        <div
          key={index}
          className="h-[292px] animate-pulse rounded-2xl border border-white/6 bg-white/[0.02] p-5"
        >
          <div className="h-3 w-24 rounded bg-white/8" />
          <div className="mt-2 h-4 w-40 rounded bg-white/8" />
          <div className="mt-5 h-16 w-full rounded-xl bg-white/5" />
          <div className="mt-4 space-y-2">
            <div className="h-3 w-full rounded bg-white/5" />
            <div className="h-3 w-3/4 rounded bg-white/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function RouterPanel({ revision }: { revision?: string }) {
  const [cloudAuthorized, setCloudAuthorized] = useState(false);
  const [data, setData] = useState<RouterDecisionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const response = await api.routerDecisions(cloudAuthorized);
        setData(response);
        setError(null);
      } catch (cause) {
        setError(
          cause instanceof Error
            ? cause.message
            : "No se pudo consultar el enrutador.",
        );
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [cloudAuthorized],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh, revision]);

  return (
    <section className="space-y-3" aria-labelledby="router-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Waypoints className="size-4 text-primary" aria-hidden />
            <p className="mono-label">Decisión con estado real</p>
          </div>
          <h2 id="router-heading" className="display-title mt-1 text-xl font-semibold">
            Enrutador
          </h2>
          <p className="mt-1 max-w-2xl text-[0.78rem] leading-relaxed text-muted-foreground">
            Para cada tipo de operación, este es el editor que se elegiría ahora mismo y
            por qué se descarta el resto. Solo entran plugins instalados, habilitados y
            conectados que declaren las capacidades necesarias.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex h-9 items-center gap-2 rounded-lg border border-white/8 bg-white/[0.025] px-2.5">
            <Cloud className="size-3.5 text-muted-foreground" aria-hidden />
            <span className="text-[0.7rem] text-muted-foreground">
              Autorizar nube (Descript)
            </span>
            <Switch
              checked={cloudAuthorized}
              onCheckedChange={(checked) => setCloudAuthorized(checked)}
              aria-label="Autorizar explícitamente el envío de material a la nube para la decisión"
            />
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            Recalcular
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/8 px-4 py-3">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-[0.8rem] font-medium text-destructive">
              No se pudo calcular el enrutamiento
            </p>
            <p className="mt-0.5 text-[0.72rem] text-muted-foreground">{error}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            Reintentar
          </Button>
        </div>
      )}

      {loading && !data ? (
        <RouterSkeleton />
      ) : data ? (
        <>
          <div className="flex items-center gap-2 text-[0.66rem] text-muted-foreground">
            <CheckCircle2 className="size-3.5 text-success" aria-hidden />
            <span>
              {data.decisions.length} decisiones calculadas ·{" "}
              <span className="font-mono">cloud_authorized={String(data.cloud_authorized)}</span>
            </span>
            <Route className="ml-auto size-3.5 opacity-60" aria-hidden />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {data.decisions.map((decision) => (
              <DecisionCard key={decision.operation} decision={decision} />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}

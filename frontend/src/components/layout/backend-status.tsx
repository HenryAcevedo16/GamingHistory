"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Server, WifiOff } from "lucide-react";

import { API_BASE_URL, api } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

type Status =
  | { state: "loading" }
  | { state: "up"; health: HealthResponse }
  | { state: "down"; message: string };

export function BackendStatus() {
  const [status, setStatus] = useState<Status>({ state: "loading" });

  const load = useCallback(async () => {
    try {
      const health = await api.health();
      setStatus({ state: "up", health });
    } catch (error) {
      setStatus({
        state: "down",
        message: error instanceof Error ? error.message : "Sin conexión",
      });
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(() => void load(), 30_000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [load]);

  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.025] p-3">
      <div className="flex items-center justify-between">
        <p className="mono-label">Servicio local</p>
        <button
          type="button"
          onClick={() => void load()}
          aria-label="Actualizar estado del backend"
          className="grid size-6 place-items-center rounded-md text-muted-foreground transition hover:bg-white/8 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none"
        >
          <RefreshCw
            className={cn("size-3", status.state === "loading" && "animate-spin")}
          />
        </button>
      </div>

      {status.state === "loading" && (
        <div className="mt-2 space-y-2">
          <div className="h-3 w-2/3 animate-pulse rounded bg-white/10" />
          <div className="h-2.5 w-1/2 animate-pulse rounded bg-white/6" />
        </div>
      )}

      {status.state === "up" && (
        <div className="mt-2 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="status-dot bg-success shadow-[0_0_8px_2px_oklch(0.76_0.17_157_/_0.45)]" />
            <p className="text-xs font-medium text-foreground">API conectada</p>
          </div>
          <p className="font-mono text-[0.65rem] text-muted-foreground">
            v{status.health.version} · {status.health.plugins_found} plugins · DB{" "}
            {status.health.database}
          </p>
          <a
            href={`${API_BASE_URL}/docs`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-mono text-[0.62rem] text-primary/80 underline-offset-4 hover:text-primary hover:underline"
          >
            API docs ↗
          </a>
        </div>
      )}

      {status.state === "down" && (
        <div className="mt-2 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="status-dot bg-destructive" />
            <p className="text-xs font-medium text-destructive">API sin conexión</p>
          </div>
          <p className="text-[0.66rem] leading-snug text-muted-foreground">
            Levanta el backend en{" "}
            <span className="font-mono text-[0.62rem]">127.0.0.1:8000</span>.
          </p>
        </div>
      )}

      <div className="mt-2.5 flex items-center gap-1.5 border-t border-white/6 pt-2 text-[0.6rem] text-muted-foreground/70">
        {status.state === "up" ? (
          <Server className="size-3" aria-hidden />
        ) : (
          <WifiOff className="size-3" aria-hidden />
        )}
        <span className="font-mono">{API_BASE_URL.replace(/^https?:\/\//, "")}</span>
      </div>
    </div>
  );
}

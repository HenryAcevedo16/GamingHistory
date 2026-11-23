"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Puzzle,
  RefreshCw,
  Search,
  ServerCrash,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";

import { PermissionsDialog, type InstallIssue } from "@/components/extensions/permissions-dialog";
import { PluginCard } from "@/components/extensions/plugin-card";
import { PluginDetailSheet } from "@/components/extensions/plugin-detail-sheet";
import { RouterPanel } from "@/components/extensions/router-panel";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type {
  DiagnosticResponse,
  PluginCounts,
  PluginListResponse,
  PluginView,
  RequirementReport,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type TabValue = "available" | "installed" | "connected";

type Feedback = {
  tone: "success" | "warning" | "error";
  message: string;
  details?: string[];
};

function feedbackFromError(error: unknown): Feedback {
  if (error instanceof ApiError) {
    const checks = Array.isArray((error.details as { checks?: unknown })?.checks)
      ? ((error.details as { checks: { label: string; evidence: string }[] }).checks ?? [])
      : [];
    return {
      tone: "error",
      message: error.message,
      details: checks.map((check) => `${check.label}: ${check.evidence}`),
    };
  }
  return {
    tone: "error",
    message: error instanceof Error ? error.message : "Ocurrió un error inesperado.",
  };
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
}) {
  return (
    <div className="glass-panel relative overflow-hidden rounded-2xl px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="mono-label">{label}</p>
          <p className="mt-1.5 font-display text-2xl font-semibold tabular-nums">{value}</p>
          <p className="mt-0.5 text-[0.66rem] text-muted-foreground">{hint}</p>
        </div>
        <span
          className={cn(
            "grid size-8 place-items-center rounded-lg border border-white/8 bg-white/[0.03]",
            accent,
          )}
        >
          <Icon className="size-4" />
        </span>
      </div>
    </div>
  );
}

function CardsSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div
          key={index}
          className="h-[248px] animate-pulse rounded-2xl border border-white/6 bg-white/[0.02] p-5"
        >
          <div className="flex gap-3">
            <div className="size-12 rounded-xl bg-white/8" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-1/2 rounded bg-white/8" />
              <div className="h-3 w-1/3 rounded bg-white/5" />
            </div>
          </div>
          <div className="mt-5 space-y-2">
            <div className="h-3 w-full rounded bg-white/5" />
            <div className="h-3 w-4/5 rounded bg-white/5" />
          </div>
          <div className="mt-6 flex justify-between">
            <div className="h-6 w-24 rounded-full bg-white/5" />
            <div className="h-7 w-28 rounded-lg bg-white/8" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ExtensionsView() {
  const [data, setData] = useState<PluginListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabValue>("available");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [pendingInstall, setPendingInstall] = useState<PluginView | null>(null);
  const [installBusy, setInstallBusy] = useState(false);
  const [installError, setInstallError] = useState<InstallIssue | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<Record<string, DiagnosticResponse>>({});
  const [requirements, setRequirements] = useState<Record<string, RequirementReport>>({});
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const response = await api.listPlugins();
      setData(response);
      setLoadError(null);
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "No se pudo cargar el catálogo de plugins.",
      );
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(initial);
  }, [refresh]);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(null), 10_000);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const items = useMemo(() => data?.items ?? [], [data]);
  const counts: PluginCounts =
    data?.counts ?? {
      total: 0,
      available: 0,
      installed: 0,
      connected: 0,
      disabled: 0,
      error: 0,
    };

  const installedTotal = counts.total - counts.available;
  const attentionTotal = counts.error + counts.disabled;

  const tabCounts: Record<TabValue, number> = {
    available: counts.available,
    installed: installedTotal,
    connected: counts.connected,
  };

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return items
      .filter((plugin) => {
        if (tab === "available") return plugin.display_status === "available";
        if (tab === "connected") return plugin.connected;
        return plugin.install_status !== "not_installed";
      })
      .filter((plugin) => {
        if (!term) return true;
        return [plugin.name, plugin.description, plugin.category, plugin.id]
          .join(" ")
          .toLowerCase()
          .includes(term);
      });
  }, [items, tab, query]);

  const selectedPlugin = selectedId
    ? (items.find((plugin) => plugin.id === selectedId) ?? null)
    : null;

  const [busyPluginId, busyActionName] = busy ? busy.split(":") : [null, null];
  const actionNames = new Set(["install", "connect", "disconnect", "enable", "disable"]);
  const detailBusyAction =
    selectedPlugin && busyPluginId === selectedPlugin.id && busyActionName && actionNames.has(busyActionName)
      ? (busyActionName as "install" | "connect" | "disconnect" | "enable" | "disable")
      : null;

  const runAction = useCallback(
    async (
      pluginId: string,
      action: "connect" | "disconnect" | "enable" | "disable",
      request: () => Promise<{ message: string }>,
    ) => {
      setBusy(`${pluginId}:${action}`);
      try {
        const response = await request();
        await refresh(true);
        setFeedback({ tone: "success", message: response.message });
      } catch (error) {
        setFeedback(feedbackFromError(error));
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const runDiagnose = useCallback(
    async (pluginId: string) => {
      setBusy(`${pluginId}:diagnose`);
      try {
        const report = await api.diagnose(pluginId);
        setDiagnostics((current) => ({ ...current, [pluginId]: report }));
        await refresh(true);
        setFeedback({
          tone: report.ok ? "success" : "warning",
          message: report.ok
            ? "Diagnóstico correcto: todas las comprobaciones obligatorias pasaron."
            : `Diagnóstico con ${report.summary.failed} fallo(s). Revisa la evidencia.`,
        });
      } catch (error) {
        setFeedback(feedbackFromError(error));
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const runVerify = useCallback(
    async (pluginId: string) => {
      setBusy(`${pluginId}:verify`);
      try {
        const report = await api.verifyRequirements(pluginId);
        setRequirements((current) => ({ ...current, [pluginId]: report }));
        await refresh(true);
        setFeedback({
          tone: report.ok ? "success" : "warning",
          message: report.ok
            ? "Requisitos verificados correctamente."
            : "Hay requisitos sin satisfacer. Revisa la evidencia de cada comprobación.",
        });
      } catch (error) {
        setFeedback(feedbackFromError(error));
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const openPermissions = useCallback((plugin: PluginView) => {
    setInstallError(null);
    setPendingInstall(plugin);
  }, []);

  const confirmInstall = useCallback(async () => {
    if (!pendingInstall) return;
    setInstallBusy(true);
    setInstallError(null);
    try {
      const response = await api.install(pendingInstall.id, true);
      await refresh(true);
      setPendingInstall(null);
      setFeedback({ tone: "success", message: response.message });
    } catch (error) {
      if (error instanceof ApiError) {
        const checks = Array.isArray((error.details as { checks?: unknown })?.checks)
          ? (error.details as { checks: { id: string; label: string; evidence: string; hint?: string }[] })
              .checks
          : undefined;
        setInstallError({ message: error.message, checks });
      } else {
        setInstallError({
          message: error instanceof Error ? error.message : "La instalación falló.",
        });
      }
    } finally {
      setInstallBusy(false);
    }
  }, [pendingInstall, refresh]);

  const tabs: { value: TabValue; label: string }[] = [
    { value: "available", label: "Disponibles" },
    { value: "installed", label: "Instalados" },
    { value: "connected", label: "Conectados" },
  ];

  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 md:px-8 md:py-8">
      <div className="space-y-6">
        <header className="flex flex-col gap-5 border-b border-white/6 pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="status-dot bg-primary shadow-[0_0_8px_2px_oklch(0.64_0.245_296_/_0.5)]" />
              <p className="mono-label">Centro de control · Extensiones</p>
            </div>
            <h1 className="display-title mt-2 text-3xl font-semibold sm:text-4xl">
              Extensiones
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
              Conecta tus herramientas de edición. Cada diagnóstico ejecuta comprobaciones
              reales en esta máquina y muestra la evidencia; nada se marca como verificado
              sin pasar la prueba.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              onClick={() => void refresh()}
              disabled={loading}
            >
              <RefreshCw className={cn("size-4", loading && "animate-spin")} />
              Actualizar
            </Button>
          </div>
        </header>

        <AnimatePresence initial={false}>
          {feedback && (
            <motion.div
              key={feedback.message + feedback.tone}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div
                className={cn(
                  "flex items-start gap-2.5 rounded-xl border px-4 py-3",
                  feedback.tone === "success" &&
                    "border-success/25 bg-success/8 text-success",
                  feedback.tone === "warning" &&
                    "border-warning/25 bg-warning/8 text-warning",
                  feedback.tone === "error" &&
                    "border-destructive/30 bg-destructive/8 text-destructive",
                )}
              >
                {feedback.tone === "success" ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
                ) : (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-[0.82rem] leading-snug font-medium">{feedback.message}</p>
                  {feedback.details && feedback.details.length > 0 && (
                    <ul className="mt-1.5 space-y-0.5">
                      {feedback.details.map((detail, index) => (
                        <li
                          key={index}
                          className="break-words font-mono text-[0.66rem] text-muted-foreground"
                        >
                          {detail}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setFeedback(null)}
                  aria-label="Cerrar aviso"
                  className="rounded-md p-1 text-current/70 transition hover:bg-white/8 hover:text-current focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {loadError && (
          <div className="flex flex-col gap-3 rounded-2xl border border-destructive/30 bg-destructive/8 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2.5">
              <ServerCrash className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
              <div>
                <p className="text-sm font-medium text-destructive">
                  No se pudo cargar el catálogo real de plugins
                </p>
                <p className="mt-1 text-[0.76rem] leading-relaxed text-muted-foreground">
                  {loadError}
                </p>
                <p className="mt-1 font-mono text-[0.64rem] text-muted-foreground/70">
                  cd backend ; .\.venv\Scripts\python -m uvicorn app.main:app --reload
                </p>
              </div>
            </div>
            <Button variant="outline" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw className={cn("size-4", loading && "animate-spin")} />
              Reintentar
            </Button>
          </div>
        )}

        {data?.manifest_errors && data.manifest_errors.length > 0 && (
          <div className="rounded-xl border border-warning/25 bg-warning/8 px-4 py-3">
            <p className="flex items-center gap-2 text-[0.8rem] font-medium text-warning">
              <AlertTriangle className="size-4" aria-hidden />
              {data.manifest_errors.length} manifiesto(s) con errores de validación
            </p>
            <ul className="mt-1.5 space-y-1">
              {data.manifest_errors.map((issue) => (
                <li key={issue.path} className="text-[0.7rem] text-muted-foreground">
                  <span className="font-mono">{issue.path}</span> — {issue.error}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Catálogo"
            value={counts.total}
            hint="plugins detectados en /plugins"
            icon={Puzzle}
            accent="text-primary"
          />
          <StatCard
            label="Instalados"
            value={installedTotal}
            hint="dependencias verificadas"
            icon={Sparkles}
            accent="text-info"
          />
          <StatCard
            label="Conectados"
            value={counts.connected}
            hint="con canal de ejecución real"
            icon={CheckCircle2}
            accent="text-success"
          />
          <StatCard
            label="Atención"
            value={attentionTotal}
            hint="desactivados o con error"
            icon={AlertTriangle}
            accent="text-warning"
          />
        </div>

        <RouterPanel revision={data?.generated_at} />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div
            role="tablist"
            aria-label="Filtrar extensiones"
            className="inline-flex flex-wrap items-center gap-1 rounded-xl border border-white/8 bg-white/[0.025] p-1"
          >
            {tabs.map((item) => {
              const active = tab === item.value;
              return (
                <button
                  key={item.value}
                  role="tab"
                  aria-selected={active}
                  onClick={() => setTab(item.value)}
                  className={cn(
                    "flex h-8 items-center gap-2 rounded-lg px-3 text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none",
                    active
                      ? "bg-white/[0.07] text-foreground shadow-[inset_0_1px_0_oklch(1_0_0_/_6%)]"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                  <span
                    className={cn(
                      "rounded-full px-1.5 py-0.5 font-mono text-[0.6rem]",
                      active
                        ? "bg-primary/18 text-primary"
                        : "bg-white/6 text-muted-foreground",
                    )}
                  >
                    {tabCounts[item.value]}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar extensión…"
              aria-label="Buscar extensión"
              className="h-9 w-full rounded-lg border border-white/10 bg-white/[0.03] pr-8 pl-8 text-sm placeholder:text-muted-foreground/60 focus:border-primary/40 focus:ring-2 focus:ring-ring/30 focus:outline-none"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label="Limpiar búsqueda"
                className="absolute top-1/2 right-2 grid size-5 -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:bg-white/8 hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            )}
          </div>
        </div>

        {loading && !data ? (
          <CardsSkeleton />
        ) : filtered.length === 0 ? (
          <div className="glass-panel flex flex-col items-center gap-3 rounded-2xl px-6 py-14 text-center">
            <span className="grid size-12 place-items-center rounded-2xl border border-white/8 bg-white/[0.03]">
              <Puzzle className="size-5 text-muted-foreground" />
            </span>
            <div>
              <p className="font-display text-base font-medium">
                {query
                  ? "Ningún plugin coincide con la búsqueda"
                  : tab === "connected"
                    ? "Todavía no hay plugins conectados"
                    : tab === "installed"
                      ? "Todavía no hay plugins instalados"
                      : "No quedan plugins disponibles"}
              </p>
              <p className="mx-auto mt-1 max-w-md text-[0.78rem] leading-relaxed text-muted-foreground">
                {tab === "connected"
                  ? "Conecta un plugin instalado y su diagnóstico real pasará a formar parte del estado del sistema."
                  : tab === "installed"
                    ? "Instala una extensión desde la pestaña Disponibles. La instalación exige verificar sus dependencias reales."
                    : "Revisa los errores de manifiesto o añade una nueva carpeta con manifest.json en /plugins."}
              </p>
            </div>
            {query && (
              <Button variant="outline" size="sm" onClick={() => setQuery("")}>
                Limpiar búsqueda
              </Button>
            )}
          </div>
        ) : (
          <motion.div
            layout
            className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3"
          >
            <AnimatePresence mode="popLayout">
              {filtered.map((plugin) => (
                <PluginCard
                  key={plugin.id}
                  plugin={plugin}
                  report={diagnostics[plugin.id]}
                  busy={busyPluginId === plugin.id}
                  onSelect={() => {
                    setSelectedId(plugin.id);
                    setSheetOpen(true);
                  }}
                  onInstall={() => openPermissions(plugin)}
                  onConnect={() =>
                    void runAction(plugin.id, "connect", () => api.connect(plugin.id))
                  }
                  onDisconnect={() =>
                    void runAction(plugin.id, "disconnect", () => api.disconnect(plugin.id))
                  }
                  onEnable={() =>
                    void runAction(plugin.id, "enable", () => api.enable(plugin.id))
                  }
                />
              ))}
            </AnimatePresence>
          </motion.div>
        )}

        <footer className="flex items-start gap-2 rounded-xl border border-white/6 bg-white/[0.015] px-4 py-3">
          <Terminal className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-[0.7rem] leading-relaxed text-muted-foreground">
            Los diagnósticos ejecutan binarios y sondas locales reales (por ejemplo{" "}
            <span className="font-mono">ffmpeg -version</span>, HTTP a VectCutAPI o rutas de
            DaVinci Resolve). Si una herramienta no está instalada, la propia interfaz y el
            backend lo reportan como fallo, sin simular éxito.
          </p>
        </footer>
      </div>

      <PermissionsDialog
        plugin={pendingInstall}
        open={pendingInstall !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPendingInstall(null);
            setInstallError(null);
          }
        }}
        onConfirm={() => void confirmInstall()}
        busy={installBusy}
        error={installError}
      />

      <PluginDetailSheet
        plugin={selectedPlugin}
        open={sheetOpen && selectedPlugin !== null}
        onOpenChange={(open) => {
          setSheetOpen(open);
        }}
        busyAction={detailBusyAction}
        diagnosing={selectedPlugin ? busy === `${selectedPlugin.id}:diagnose` : false}
        verifying={selectedPlugin ? busy === `${selectedPlugin.id}:verify` : false}
        report={selectedPlugin ? diagnostics[selectedPlugin.id] : null}
        requirementReport={selectedPlugin ? requirements[selectedPlugin.id] : null}
        onInstall={() => selectedPlugin && openPermissions(selectedPlugin)}
        onConnect={() =>
          selectedPlugin && void runAction(selectedPlugin.id, "connect", () => api.connect(selectedPlugin.id))
        }
        onDisconnect={() =>
          selectedPlugin &&
          void runAction(selectedPlugin.id, "disconnect", () => api.disconnect(selectedPlugin.id))
        }
        onEnable={() =>
          selectedPlugin && void runAction(selectedPlugin.id, "enable", () => api.enable(selectedPlugin.id))
        }
        onDisable={() =>
          selectedPlugin && void runAction(selectedPlugin.id, "disable", () => api.disable(selectedPlugin.id))
        }
        onDiagnose={() => selectedPlugin && void runDiagnose(selectedPlugin.id)}
        onVerify={() => selectedPlugin && void runVerify(selectedPlugin.id)}
      />
    </div>
  );
}

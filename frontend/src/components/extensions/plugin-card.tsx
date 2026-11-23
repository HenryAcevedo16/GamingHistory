"use client";

import type { CSSProperties } from "react";
import { motion } from "framer-motion";
import {
  ChevronRight,
  Download,
  Loader2,
  PlugZap,
  Power,
  Unplug,
} from "lucide-react";

import {
  CostBadge,
  PluginIcon,
  StatusBadge,
  connectionLabel,
  formatDateTime,
} from "@/components/extensions/plugin-meta";
import { Button } from "@/components/ui/button";
import type { DiagnosticResponse, PluginView } from "@/lib/types";
import { cn } from "@/lib/utils";

type PrimaryAction = "install" | "connect" | "disconnect" | "enable";

function primaryFor(plugin: PluginView): {
  action: PrimaryAction;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  variant: "default" | "outline";
} {
  if (plugin.display_status === "available") {
    return { action: "install", label: "Instalar", icon: Download, variant: "default" };
  }
  if (plugin.display_status === "disabled") {
    return { action: "enable", label: "Activar", icon: Power, variant: "default" };
  }
  if (plugin.connected) {
    return { action: "disconnect", label: "Desconectar", icon: Unplug, variant: "outline" };
  }
  return { action: "connect", label: "Conectar", icon: PlugZap, variant: "default" };
}

export function PluginCard({
  plugin,
  busy,
  report,
  onSelect,
  onInstall,
  onConnect,
  onDisconnect,
  onEnable,
}: {
  plugin: PluginView;
  busy: boolean;
  report?: DiagnosticResponse | null;
  onSelect: () => void;
  onInstall: () => void;
  onConnect: () => void;
  onDisconnect: () => void;
  onEnable: () => void;
}) {
  const primary = primaryFor(plugin);
  const PrimaryIcon = primary.icon;
  const accent = plugin.accent ?? "#8b5cf6";
  const diagnosis = report
    ? { ok: report.ok, ran_at: report.ran_at }
    : plugin.last_diagnosis?.ran_at
      ? { ok: plugin.last_diagnosis.ok ?? null, ran_at: plugin.last_diagnosis.ran_at }
      : null;

  const handlePrimary = () => {
    if (primary.action === "install") onInstall();
    else if (primary.action === "connect") onConnect();
    else if (primary.action === "disconnect") onDisconnect();
    else onEnable();
  };

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -2 }}
      style={{ "--plugin-accent": accent } as CSSProperties}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`Ver detalle de ${plugin.name}`}
      className={cn(
        "group relative flex cursor-pointer flex-col rounded-2xl border border-white/8 bg-card/55 p-5 text-left",
        "transition-colors outline-none hover:border-white/16 hover:bg-card/75",
        "focus-visible:ring-2 focus-visible:ring-ring/60",
        "shadow-[0_24px_60px_-40px_oklch(0_0_0_/_0.9)]",
        "hover:shadow-[0_26px_60px_-36px_var(--plugin-accent)]",
      )}
    >
      <span
        className="pointer-events-none absolute inset-x-6 top-0 h-px opacity-70"
        style={{
          background: `linear-gradient(90deg, transparent, ${accent}88, transparent)`,
        }}
        aria-hidden
      />

      <div className="flex items-start gap-3.5">
        <PluginIcon plugin={plugin} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="font-display text-base font-semibold tracking-tight">
              {plugin.name}
            </h3>
            <span className="font-mono text-[0.62rem] text-muted-foreground">
              v{plugin.version}
            </span>
            {plugin.optional && (
              <span className="rounded border border-white/8 px-1.5 py-0.5 font-mono text-[0.55rem] tracking-wide text-muted-foreground">
                OPCIONAL
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[0.72rem] text-muted-foreground">
            {plugin.category} · {connectionLabel(plugin.connection_type)}
          </p>
        </div>
        <StatusBadge status={plugin.display_status} />
      </div>

      <p className="mt-3 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
        {plugin.description}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <CostBadge costs={plugin.known_costs} />
        <span className="inline-flex h-5 items-center rounded-full border border-white/8 bg-white/[0.03] px-2 text-[0.65rem] text-muted-foreground">
          {plugin.tools.length} herramientas
        </span>
        <span className="inline-flex h-5 items-center rounded-full border border-white/8 bg-white/[0.03] px-2 text-[0.65rem] text-muted-foreground">
          {plugin.capabilities.length} capacidades
        </span>
        {plugin.last_error && (
          <span className="inline-flex h-5 max-w-full items-center gap-1 truncate rounded-full border border-destructive/25 bg-destructive/10 px-2 text-[0.65rem] text-destructive">
            requiere atención
          </span>
        )}
      </div>

      <div className="mt-auto flex items-center justify-between gap-3 border-t border-white/6 pt-3.5">
        <div className="min-w-0">
          {diagnosis ? (
            <p className="flex items-center gap-1.5 text-[0.66rem] text-muted-foreground">
              <span
                className={cn(
                  "status-dot",
                  diagnosis.ok === true
                    ? "bg-success"
                    : diagnosis.ok === false
                      ? "bg-destructive"
                      : "bg-muted-foreground/60",
                )}
              />
              <span className="truncate">
                Diagnóstico {diagnosis.ok ? "correcto" : "con fallos"} ·{" "}
                {formatDateTime(diagnosis.ran_at)}
              </span>
            </p>
          ) : (
            <p className="text-[0.66rem] text-muted-foreground/70">
              {plugin.checks_total} comprobaciones sin ejecutar
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            onClick={(event) => {
              event.stopPropagation();
              onSelect();
            }}
            className="text-muted-foreground"
          >
            Detalle
            <ChevronRight className="size-3.5" />
          </Button>
          <Button
            size="sm"
            variant={primary.variant}
            disabled={busy}
            onClick={(event) => {
              event.stopPropagation();
              handlePrimary();
            }}
          >
            {busy ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <PrimaryIcon className="size-3.5" />
            )}
            {primary.label}
          </Button>
        </div>
      </div>
    </motion.article>
  );
}

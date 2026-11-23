"use client";

import { useState } from "react";
import { AlertTriangle, Loader2, ShieldCheck, XCircle } from "lucide-react";

import { PluginIcon, RiskBadge } from "@/components/extensions/plugin-meta";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import type { PluginView } from "@/lib/types";

export interface InstallIssue {
  message: string;
  checks?: { id: string; label: string; evidence: string; hint?: string }[];
}

export function PermissionsDialog({
  plugin,
  open,
  onOpenChange,
  onConfirm,
  busy,
  error,
}: {
  plugin: PluginView | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  busy: boolean;
  error: InstallIssue | null;
}) {
  const [ackState, setAckState] = useState<{ pluginId: string | null; ack: boolean }>(
    { pluginId: null, ack: false },
  );
  const ack = plugin && ackState.pluginId === plugin.id ? ackState.ack : false;

  if (!plugin) return null;

  const setAck = (value: boolean) =>
    setAckState({ pluginId: plugin.id, ack: value });

  const handleOpenChange = (open: boolean) => {
    if (!open) setAckState({ pluginId: null, ack: false });
    onOpenChange(open);
  };

  const requiresAck = plugin.permissions.length > 0;
  const cloudPermission = plugin.permissions.some((permission) =>
    /cloud|nube/i.test(`${permission.id} ${permission.label}`),
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="permissions-dialog">
        <DialogHeader>
          <div className="flex items-start gap-3">
            <PluginIcon plugin={plugin} />
            <div className="min-w-0">
              <p className="mono-label">Instalar extensión</p>
              <DialogTitle className="mt-1 font-display text-lg font-semibold">
                {plugin.name}
              </DialogTitle>
              <DialogDescription className="mt-1 text-[0.8rem]">
                Se verificará el plugin con comprobaciones reales antes de marcarlo como
                instalado. Si falta una dependencia, la instalación se cancela.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="max-h-[52vh] space-y-4 overflow-y-auto pr-1">
          <section>
            <p className="mono-label mb-2">Permisos solicitados</p>
            {plugin.permissions.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Este plugin no solicita permisos adicionales.
              </p>
            ) : (
              <ul className="space-y-2">
                {plugin.permissions.map((permission) => (
                  <li
                    key={permission.id}
                    className="rounded-xl border border-white/8 bg-white/[0.02] px-3 py-2.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium">{permission.label}</p>
                      <RiskBadge risk={permission.risk} />
                    </div>
                    <p className="mt-1 text-[0.74rem] leading-relaxed text-muted-foreground">
                      {permission.description}
                    </p>
                    <p className="mt-1 font-mono text-[0.6rem] text-muted-foreground/60">
                      {permission.id}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <p className="mono-label mb-2">Requisitos</p>
            <ul className="space-y-1.5">
              {plugin.requirements.map((requirement) => (
                <li
                  key={requirement.id}
                  className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-white/6 bg-white/[0.015] px-3 py-2"
                >
                  <span className="text-[0.78rem]">{requirement.label}</span>
                  <span className="rounded border border-white/8 px-1.5 py-0.5 font-mono text-[0.56rem] text-muted-foreground">
                    {requirement.kind}
                  </span>
                  {requirement.optional ? (
                    <span className="font-mono text-[0.56rem] text-muted-foreground/70">
                      opcional
                    </span>
                  ) : (
                    <span className="font-mono text-[0.56rem] text-warning">obligatorio</span>
                  )}
                  <span className="ml-auto max-w-full truncate font-mono text-[0.58rem] text-muted-foreground/60">
                    {requirement.identifier}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {cloudPermission && (
            <div className="flex items-start gap-2 rounded-xl border border-warning/25 bg-warning/8 px-3 py-2.5">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
              <p className="text-[0.74rem] leading-relaxed text-warning/90">
                Este plugin puede enviar material a la nube. Nada se enviará sin
                autorización explícita por proyecto; instalar la extensión no autoriza
                subidas.
              </p>
            </div>
          )}

          <div className="rounded-xl border border-white/8 bg-white/[0.02] px-3 py-2.5">
            <p className="mono-label mb-1">Coste conocido</p>
            <p className="text-[0.76rem] leading-relaxed text-muted-foreground">
              {plugin.known_costs.notes}
            </p>
            {plugin.known_costs.limits && (
              <p className="mt-1 text-[0.7rem] text-muted-foreground/70">
                Límites: {plugin.known_costs.limits}
              </p>
            )}
          </div>

          {requiresAck && (
            <div className="flex items-center justify-between gap-4 rounded-xl border border-primary/20 bg-primary/8 px-3.5 py-3">
              <div className="flex items-start gap-2">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                <p className="text-[0.78rem] leading-snug">
                  Autorizo estos permisos para este plugin y entiendo que el diagnóstico
                  se ejecutará en mi equipo.
                </p>
              </div>
              <Switch
                checked={ack}
                onCheckedChange={(checked) => setAck(checked)}
                aria-label="Autorizar permisos del plugin"
              />
            </div>
          )}

          {error && (
            <div className="space-y-2 rounded-xl border border-destructive/30 bg-destructive/8 px-3.5 py-3">
              <div className="flex items-start gap-2">
                <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
                <p className="text-[0.8rem] leading-snug text-destructive">{error.message}</p>
              </div>
              {error.checks && error.checks.length > 0 && (
                <ul className="space-y-1 pl-6">
                  {error.checks.map((check) => (
                    <li key={check.id} className="text-[0.7rem] text-muted-foreground">
                      <span className="font-medium text-foreground/80">{check.label}:</span>{" "}
                      <span className="break-words font-mono text-[0.65rem]">
                        {check.evidence}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => handleOpenChange(false)} disabled={busy}>
            Cancelar
          </Button>
          <Button
            onClick={onConfirm}
            disabled={busy || (requiresAck && !ack)}
            className="min-w-28"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : null}
            {busy ? "Verificando…" : "Instalar plugin"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

"use client";

import {
  Activity,
  CheckCircle2,
  Download,
  ExternalLink,
  Loader2,
  PlugZap,
  Power,
  ShieldCheck,
  Terminal,
  Unplug,
  Wrench,
  XCircle,
} from "lucide-react";

import { DiagnosticResults } from "@/components/extensions/diagnostic-results";
import {
  CHECK_META,
  CostBadge,
  PluginIcon,
  RiskBadge,
  StatusBadge,
  connectionLabel,
  formatDateTime,
} from "@/components/extensions/plugin-meta";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import type {
  CheckStatus,
  DiagnosticResponse,
  PluginView,
  RequirementReport,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type BusyAction = "install" | "connect" | "disconnect" | "enable" | "disable" | null;

function Section({
  icon: Icon,
  title,
  count,
  action,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  count?: number;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2.5">
      <div className="flex items-center gap-2">
        <Icon className="size-3.5 text-muted-foreground" aria-hidden />
        <h3 className="mono-label text-foreground/70">{title}</h3>
        {typeof count === "number" && (
          <span className="rounded-full border border-white/8 px-1.5 py-0.5 font-mono text-[0.56rem] text-muted-foreground">
            {count}
          </span>
        )}
        {action && <div className="ml-auto">{action}</div>}
      </div>
      {children}
    </section>
  );
}

function RequirementStatusIcon({ status }: { status?: CheckStatus | null }) {
  if (!status) {
    return <span className="status-dot mt-1.5 bg-muted-foreground/40" />;
  }
  const meta = CHECK_META[status];
  const Icon = meta.icon;
  return <Icon className={cn("mt-0.5 size-4 shrink-0", meta.className)} aria-hidden />;
}

export function PluginDetailSheet({
  plugin,
  open,
  onOpenChange,
  busyAction,
  diagnosing,
  verifying,
  report,
  requirementReport,
  onInstall,
  onConnect,
  onDisconnect,
  onEnable,
  onDisable,
  onDiagnose,
  onVerify,
}: {
  plugin: PluginView | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busyAction: BusyAction;
  diagnosing: boolean;
  verifying: boolean;
  report?: DiagnosticResponse | null;
  requirementReport?: RequirementReport | null;
  onInstall: () => void;
  onConnect: () => void;
  onDisconnect: () => void;
  onEnable: () => void;
  onDisable: () => void;
  onDiagnose: () => void;
  onVerify: () => void;
}) {
  if (!plugin) return null;

  const requirementChecks = new Map(
    (requirementReport?.checks ?? report?.checks ?? []).map((check) => [check.id, check]),
  );
  const busy = busyAction !== null || diagnosing || verifying;
  const canDeactivate =
    plugin.install_status !== "not_installed" && plugin.display_status !== "disabled";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="plugin-sheet gap-0 p-0">
        <SheetTitle className="sr-only">Detalle de {plugin.name}</SheetTitle>

        <div className="shrink-0 border-b border-white/8 px-5 pt-6 pb-5 sm:px-6">
          <div className="flex items-start gap-4">
            <PluginIcon plugin={plugin} size="lg" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-display text-2xl font-semibold tracking-tight">
                  {plugin.name}
                </h2>
                <span className="rounded border border-white/8 px-1.5 py-0.5 font-mono text-[0.6rem] text-muted-foreground">
                  v{plugin.version}
                </span>
                {plugin.optional && (
                  <span className="rounded border border-white/8 px-1.5 py-0.5 font-mono text-[0.55rem] tracking-wide text-muted-foreground">
                    OPCIONAL
                  </span>
                )}
              </div>
              <p className="mt-1 text-[0.78rem] text-muted-foreground">
                {plugin.category} · {connectionLabel(plugin.connection_type)}
              </p>
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                <StatusBadge status={plugin.display_status} />
                <CostBadge costs={plugin.known_costs} />
                <span className="font-mono text-[0.62rem] text-muted-foreground">
                  {plugin.id}
                </span>
              </div>
            </div>
          </div>

          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {plugin.description}
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {plugin.display_status === "available" && (
              <Button onClick={onInstall} disabled={busy}>
                {busyAction === "install" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Download className="size-4" />
                )}
                Instalar plugin
              </Button>
            )}

            {(plugin.display_status === "installed" || plugin.display_status === "error") && (
              <Button onClick={onConnect} disabled={busy}>
                {busyAction === "connect" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <PlugZap className="size-4" />
                )}
                Conectar
              </Button>
            )}

            {plugin.display_status === "connected" && (
              <Button variant="outline" onClick={onDisconnect} disabled={busy}>
                {busyAction === "disconnect" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Unplug className="size-4" />
                )}
                Desconectar
              </Button>
            )}

            {plugin.display_status === "disabled" && (
              <Button onClick={onEnable} disabled={busy}>
                {busyAction === "enable" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Power className="size-4" />
                )}
                Activar
              </Button>
            )}

            {canDeactivate && (
              <Button variant="ghost" onClick={onDisable} disabled={busy}>
                {busyAction === "disable" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Power className="size-4" />
                )}
                Desactivar
              </Button>
            )}

            {plugin.documentation_url && (
              <Button
                variant="ghost"
                render={
                  <a
                    href={plugin.documentation_url}
                    target="_blank"
                    rel="noreferrer"
                  />
                }
              >
                Documentación
                <ExternalLink className="size-3.5" />
              </Button>
            )}
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-5 sm:px-6">
          {plugin.last_error && (
            <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/8 px-3.5 py-3">
              <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
              <div>
                <p className="text-[0.78rem] font-medium text-destructive">
                  Último error registrado
                </p>
                <p className="mt-0.5 text-[0.74rem] leading-relaxed text-muted-foreground">
                  {plugin.last_error}
                </p>
              </div>
            </div>
          )}

          <Section icon={ShieldCheck} title="Requisitos" count={plugin.requirements.length}>
            <ul className="space-y-1.5">
              {plugin.requirements.map((requirement) => {
                const check = requirement.check_id
                  ? requirementChecks.get(requirement.check_id)
                  : undefined;
                return (
                  <li
                    key={requirement.id}
                    className="rounded-xl border border-white/7 bg-white/[0.02] px-3 py-2.5"
                  >
                    <div className="flex items-start gap-2">
                      <RequirementStatusIcon status={check?.status ?? null} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="text-[0.8rem] font-medium">
                            {requirement.label}
                          </span>
                          <span className="rounded border border-white/8 px-1.5 py-0.5 font-mono text-[0.55rem] text-muted-foreground">
                            {requirement.kind}
                          </span>
                          {requirement.optional ? (
                            <span className="font-mono text-[0.55rem] text-muted-foreground/70">
                              opcional
                            </span>
                          ) : (
                            <span className="font-mono text-[0.55rem] text-warning">
                              obligatorio
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 break-all font-mono text-[0.62rem] text-muted-foreground/80">
                          {requirement.identifier}
                        </p>
                        {requirement.notes && (
                          <p className="mt-1 text-[0.7rem] leading-snug text-muted-foreground/70">
                            {requirement.notes}
                          </p>
                        )}
                        {check && (
                          <p
                            className={cn(
                              "mt-1 break-words font-mono text-[0.62rem]",
                              check.status === "fail"
                                ? "text-destructive/90"
                                : "text-muted-foreground",
                            )}
                          >
                            {check.evidence}
                          </p>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
            <Button
              variant="outline"
              size="sm"
              onClick={onVerify}
              disabled={verifying}
              className="mt-1"
            >
              {verifying ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="size-3.5" />
              )}
              Verificar dependencias
            </Button>
          </Section>

          <Section icon={Wrench} title="Herramientas" count={plugin.tools.length}>
            <ul className="space-y-1.5">
              {plugin.tools.map((tool) => (
                <li
                  key={tool.name}
                  className="rounded-lg border border-white/6 bg-white/[0.015] px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[0.7rem] text-foreground/90">
                      {tool.name}
                    </span>
                    {tool.destructive && (
                      <span className="rounded border border-destructive/25 bg-destructive/8 px-1.5 py-0.5 font-mono text-[0.52rem] text-destructive">
                        destructivo
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[0.72rem] leading-snug text-muted-foreground">
                    {tool.description}
                  </p>
                </li>
              ))}
            </ul>
          </Section>

          <Section
            icon={Activity}
            title="Capacidades declaradas vs. verificadas"
            count={plugin.capabilities.length}
          >
            <p className="text-[0.7rem] leading-snug text-muted-foreground/80">
              {plugin.declared_capabilities.length} declaradas en el manifiesto · {" "}
               {plugin.verified_capabilities.length} verificadas por una operación real.
               Las restantes se muestran como declaradas o no soportadas por el adaptador.
            </p>
            {plugin.adapter_notes?.map((note) => (
              <p key={note} className="text-xs text-muted-foreground">{note}</p>
            ))}
            <ul className="mt-1 grid gap-1.5 sm:grid-cols-2">
              {plugin.capabilities.map((capability) => (
                <li
                  key={capability.id}
                  className="rounded-lg border border-white/6 bg-white/[0.015] px-3 py-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[0.74rem] font-medium">{capability.label}</span>
                    <span
                      className={cn(
                        "shrink-0 rounded border px-1.5 py-0.5 font-mono text-[0.5rem]",
                        capability.status === "verified"
                          ? "border-success/25 bg-success/10 text-success"
                          : capability.status === "unsupported"
                            ? "border-destructive/25 bg-destructive/10 text-destructive"
                            : "border-white/10 bg-white/5 text-muted-foreground",
                      )}
                    >
                      {capability.status === "verified"
                        ? "verificada"
                        : capability.status === "unsupported"
                          ? "no soportada"
                          : "declarada"}
                    </span>
                  </div>
                  <p className="mt-0.5 font-mono text-[0.55rem] text-muted-foreground/70">
                    {capability.id}
                  </p>
                  {capability.description && (
                    <p className="mt-1 text-[0.68rem] leading-snug text-muted-foreground">
                      {capability.description}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </Section>

          <Section icon={ShieldCheck} title="Permisos" count={plugin.permissions.length}>
            <ul className="space-y-1.5">
              {plugin.permissions.map((permission) => (
                <li
                  key={permission.id}
                  className="rounded-lg border border-white/6 bg-white/[0.015] px-3 py-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[0.76rem] font-medium">{permission.label}</span>
                    <RiskBadge risk={permission.risk} />
                  </div>
                  <p className="mt-1 text-[0.7rem] leading-snug text-muted-foreground">
                    {permission.description}
                  </p>
                </li>
              ))}
            </ul>
          </Section>

          <Section
            icon={Terminal}
            title="Diagnóstico"
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={onDiagnose}
                disabled={diagnosing}
              >
                {diagnosing ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Terminal className="size-3.5" />
                )}
                Ejecutar diagnóstico
              </Button>
            }
          >
            <DiagnosticResults
              report={report}
              running={diagnosing}
              emptyLabel={
                plugin.last_diagnosis?.ran_at
                  ? `Último diagnóstico guardado: ${formatDateTime(
                      plugin.last_diagnosis.ran_at,
                    )} (${plugin.last_diagnosis.ok ? "correcto" : "con fallos"}). Ejecuta de nuevo para ver el detalle actual.`
                  : "Todavía no se ejecutó ningún diagnóstico para este plugin."
              }
            />
          </Section>

          <Section icon={Terminal} title="Datos de conexión">
            <dl className="grid gap-2 text-[0.72rem] sm:grid-cols-2">
              <div className="rounded-lg border border-white/6 bg-white/[0.015] px-3 py-2">
                <dt className="mono-label">Comando / endpoint</dt>
                <dd className="mt-1 break-all font-mono text-[0.65rem] text-foreground/85">
                  {plugin.mcp_command_or_endpoint ?? "No declarado"}
                </dd>
              </div>
              <div className="rounded-lg border border-white/6 bg-white/[0.015] px-3 py-2">
                <dt className="mono-label">Tipo de conexión</dt>
                <dd className="mt-1 font-mono text-[0.65rem] text-foreground/85">
                  {plugin.connection_type}
                </dd>
              </div>
              <div className="rounded-lg border border-white/6 bg-white/[0.015] px-3 py-2">
                <dt className="mono-label">Instalado</dt>
                <dd className="mt-1 text-[0.7rem] text-foreground/85">
                  {plugin.installed_at ? formatDateTime(plugin.installed_at) : "—"}
                </dd>
              </div>
              <div className="rounded-lg border border-white/6 bg-white/[0.015] px-3 py-2">
                <dt className="mono-label">Conectado</dt>
                <dd className="mt-1 text-[0.7rem] text-foreground/85">
                  {plugin.connected_at ? formatDateTime(plugin.connected_at) : "—"}
                </dd>
              </div>
            </dl>
          </Section>
        </div>
      </SheetContent>
    </Sheet>
  );
}

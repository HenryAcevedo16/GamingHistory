import type { CSSProperties } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleMinus,
  CircleSlash,
  XCircle,
} from "lucide-react";

import type {
  CheckStatus,
  DisplayStatus,
  KnownCosts,
  PluginView,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export const STATUS_META: Record<
  DisplayStatus,
  { label: string; dot: string; badge: string; pulse?: boolean }
> = {
  available: {
    label: "Disponible",
    dot: "bg-muted-foreground/60",
    badge: "border-white/10 bg-white/5 text-muted-foreground",
  },
  installed: {
    label: "Instalado",
    dot: "bg-primary",
    badge: "border-primary/25 bg-primary/12 text-primary",
  },
  connected: {
    label: "Conectado",
    dot: "bg-success shadow-[0_0_8px_2px_oklch(0.76_0.17_157_/_0.5)]",
    badge: "border-success/25 bg-success/12 text-success",
    pulse: true,
  },
  disabled: {
    label: "Desactivado",
    dot: "bg-warning",
    badge: "border-warning/25 bg-warning/12 text-warning",
  },
  error: {
    label: "Error",
    dot: "bg-destructive",
    badge: "border-destructive/30 bg-destructive/12 text-destructive",
  },
};

export function StatusBadge({
  status,
  className,
}: {
  status: DisplayStatus;
  className?: string;
}) {
  const meta = STATUS_META[status];
  return (
    <span
      className={cn(
        "inline-flex h-5.5 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[0.7rem] font-medium whitespace-nowrap",
        meta.badge,
        className,
      )}
    >
      <span className={cn("status-dot", meta.dot)} />
      {meta.label}
    </span>
  );
}

export function PluginIcon({
  plugin,
  size = "md",
}: {
  plugin: PluginView;
  size?: "sm" | "md" | "lg";
}) {
  const accent = plugin.accent ?? "#8b5cf6";
  const style = {
    "--plugin-accent": accent,
    backgroundColor: `${accent}18`,
    borderColor: `${accent}3d`,
    color: accent,
    boxShadow: `inset 0 1px 0 oklch(1 0 0 / 8%), 0 10px 30px -18px ${accent}`,
  } as CSSProperties;

  const dimensions =
    size === "lg"
      ? "size-14 text-lg rounded-2xl"
      : size === "sm"
        ? "size-9 text-[0.65rem] rounded-lg"
        : "size-12 text-sm rounded-xl";

  return (
    <div
      aria-hidden
      style={style}
      className={cn(
        "grid shrink-0 place-items-center border font-mono font-semibold tracking-[0.08em]",
        dimensions,
      )}
    >
      {(plugin.icon ?? plugin.name.slice(0, 2)).toUpperCase()}
    </div>
  );
}

const COST_META: Record<
  KnownCosts["pricing"],
  { label: string; className: string }
> = {
  free: { label: "Gratis", className: "border-success/20 bg-success/10 text-success" },
  freemium: {
    label: "Freemium",
    className: "border-info/20 bg-info/10 text-info",
  },
  paid: { label: "De pago", className: "border-warning/20 bg-warning/10 text-warning" },
  unknown: {
    label: "Coste desconocido",
    className: "border-white/10 bg-white/5 text-muted-foreground",
  },
};

export function CostBadge({ costs }: { costs: KnownCosts }) {
  const meta = COST_META[costs.pricing] ?? COST_META.unknown;
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full border px-2 text-[0.65rem] font-medium",
        meta.className,
      )}
      title={costs.notes}
    >
      {meta.label}
    </span>
  );
}

const RISK_META = {
  low: { label: "Riesgo bajo", className: "border-white/10 bg-white/5 text-muted-foreground" },
  medium: { label: "Riesgo medio", className: "border-warning/25 bg-warning/10 text-warning" },
  high: { label: "Riesgo alto", className: "border-destructive/30 bg-destructive/10 text-destructive" },
};

export function RiskBadge({ risk }: { risk: "low" | "medium" | "high" }) {
  const meta = RISK_META[risk];
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full border px-2 text-[0.62rem] font-medium whitespace-nowrap",
        meta.className,
      )}
    >
      {meta.label}
    </span>
  );
}

export const CHECK_META: Record<
  CheckStatus,
  { label: string; icon: React.ComponentType<{ className?: string }>; className: string }
> = {
  pass: { label: "OK", icon: CheckCircle2, className: "text-success" },
  fail: { label: "Fallo", icon: XCircle, className: "text-destructive" },
  warn: { label: "Aviso", icon: AlertTriangle, className: "text-warning" },
  skip: { label: "Omitida", icon: CircleMinus, className: "text-muted-foreground" },
};

export const CONNECTION_LABEL: Record<string, string> = {
  "local-binary": "Binario local",
  "mcp-stdio": "MCP stdio",
  "mcp-http": "MCP HTTP",
  "cloud-api": "API en la nube",
};

export function connectionLabel(value: string) {
  return CONNECTION_LABEL[value] ?? value;
}

export function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("es", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function EmptyIcon() {
  return <CircleSlash className="size-6 text-muted-foreground" aria-hidden />;
}

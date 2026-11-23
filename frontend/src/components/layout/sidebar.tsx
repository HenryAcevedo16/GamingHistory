"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  FolderKanban,
  History,
  LayoutDashboard,
  ListChecks,
  Puzzle,
} from "lucide-react";

import { BackendStatus } from "@/components/layout/backend-status";
import { cn } from "@/lib/utils";

type NavItem = {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  href?: string;
  phase?: string;
};

const NAV_ITEMS: NavItem[] = [
  { label: "Extensiones", icon: Puzzle, href: "/extensions" },
  { label: "Dashboard", icon: LayoutDashboard, phase: "Fase 2" },
  { label: "Proyectos", icon: FolderKanban, phase: "Fase 2" },
  { label: "Trabajos", icon: ListChecks, phase: "Fase 4" },
  { label: "Auditoría", icon: History, phase: "Fase 8" },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-full flex-col border-r border-white/8 bg-[oklch(0.118_0.016_282_/_0.86)] backdrop-blur-2xl">
      <div className="flex items-center gap-3 px-5 pt-6 pb-7">
        <div className="relative grid size-11 place-items-center rounded-xl bg-primary/15 text-primary ring-1 ring-primary/30">
          <div className="absolute inset-0 rounded-xl bg-primary/20 blur-xl" aria-hidden />
          <svg viewBox="0 0 24 24" fill="none" className="relative size-5" aria-hidden>
            <path
              d="M4 5h16v14H4zM8 5v14M16 5v14M4 9h4M4 14h4M16 9h4M16 14h4M10 9.5l4 2.5-4 2.5v-5Z"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="min-w-0 leading-tight">
          <p className="font-mono text-[0.55rem] uppercase tracking-[0.22em] text-muted-foreground">
            Gaming History
          </p>
          <p className="font-display text-lg font-semibold tracking-tight">Studio</p>
        </div>
      </div>

      <nav className="flex-1 space-y-6 px-3">
        <div>
          <p className="mono-label px-3 pb-2">Espacio de trabajo</p>
          <ul className="space-y-1">
            {NAV_ITEMS.slice(0, 1).map((item) => (
              <NavRow
                key={item.label}
                item={item}
                active={pathname === item.href}
                onNavigate={onNavigate}
              />
            ))}
          </ul>
        </div>

        <div>
          <p className="mono-label px-3 pb-2">Centro de control</p>
          <ul className="space-y-1">
            {NAV_ITEMS.slice(1).map((item) => (
              <NavRow
                key={item.label}
                item={item}
                active={false}
                onNavigate={onNavigate}
              />
            ))}
          </ul>
        </div>
      </nav>

      <div className="space-y-3 px-3 pb-4">
        <BackendStatus />
        <div className="flex items-center gap-2.5 rounded-xl border border-white/6 bg-white/[0.02] px-3 py-2.5">
          <Activity className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-[0.68rem] leading-snug text-muted-foreground">
            Sesión local. Nada se envía a la nube sin autorización.
          </p>
        </div>
      </div>
    </aside>
  );
}

function NavRow({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;

  if (!item.href) {
    return (
      <li>
        <div
          aria-disabled="true"
          title={`Disponible en la ${item.phase}`}
          className="group flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground/55"
        >
          <Icon className="size-4 shrink-0" />
          <span className="flex-1 truncate">{item.label}</span>
          <span className="rounded-full border border-white/8 px-1.5 py-0.5 font-mono text-[0.55rem] tracking-wide text-muted-foreground/70">
            {item.phase}
          </span>
        </div>
      </li>
    );
  }

  return (
    <li>
      <Link
        href={item.href}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={cn(
          "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none",
          active
            ? "bg-white/[0.06] text-foreground shadow-[inset_0_1px_0_oklch(1_0_0_/_6%)]"
            : "text-muted-foreground hover:bg-white/[0.035] hover:text-foreground",
        )}
      >
        {active && (
          <span
            className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary shadow-[0_0_12px_2px_oklch(0.64_0.245_296_/_0.7)]"
            aria-hidden
          />
        )}
        <Icon
          className={cn(
            "size-4 shrink-0 transition-colors",
            active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
          )}
        />
        <span className="flex-1 truncate">{item.label}</span>
      </Link>
    </li>
  );
}

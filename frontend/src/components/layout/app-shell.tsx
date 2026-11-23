"use client";

import { useState } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

function MobileTopBar({ onMenu }: { onMenu: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between border-b border-white/8 bg-background/80 px-4 py-3 backdrop-blur-xl lg:hidden">
      <div className="flex items-center gap-2.5">
        <span className="grid size-8 place-items-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/30">
          <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden>
            <path
              d="M4 5h16v14H4zM8 5v14M16 5v14M4 9h4M4 14h4M16 9h4M16 14h4M10 9.5l4 2.5-4 2.5v-5Z"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <div className="leading-tight">
          <p className="font-mono text-[0.55rem] uppercase tracking-[0.22em] text-muted-foreground">
            Gaming History
          </p>
          <p className="font-display text-sm font-semibold">Studio</p>
        </div>
      </div>
      <button
        type="button"
        onClick={onMenu}
        aria-label="Abrir menú de navegación"
        className="grid size-9 place-items-center rounded-lg border border-white/10 bg-white/5 text-foreground transition hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none"
      >
        <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden>
          <path
            d="M4 7h16M4 12h16M4 17h16"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </header>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative min-h-dvh">
      <div className="app-grid" aria-hidden />

      <div className="fixed inset-y-0 left-0 z-40 hidden w-[264px] lg:block">
        <Sidebar />
      </div>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" showCloseButton={false} className="mobile-nav-sheet">
          <SheetTitle className="sr-only">Navegación</SheetTitle>
          <Sidebar onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      <div className="relative z-10 flex min-h-dvh flex-col lg:pl-[264px]">
        <MobileTopBar onMenu={() => setMobileOpen(true)} />
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}

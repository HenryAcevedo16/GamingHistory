"use client";

import { ArrowUpRight, FolderKanban, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { projects } from "@/lib/api";
import type { ProjectSummary } from "@/lib/timeline";
import { field, message, panel, Problem, StudioPage } from "./studio-ui";

export function ProjectsView() {
  const router = useRouter();
  const [list, setList] = useState<ProjectSummary[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [attempt, retry] = useState(0);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    projects.list().then(({ items }) => { if (active) setList(items); }, (failure) => { if (active) setLoadError(message(failure)); });
    return () => { active = false; };
  }, [attempt]);

  return <StudioPage>
    <header>
      <p className="mono-label text-primary">Espacio de trabajo / 01</p>
      <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight">Proyectos</h1>
      <p className="mt-2 text-sm text-muted-foreground">Abre una línea de tiempo o empieza un montaje local.</p>
    </header>
    <form className={panel} onSubmit={async (event) => {
      event.preventDefault();
      if (busy) return;
      setBusy(true); setError("");
      try { const project = await projects.create(name.trim()); router.push(`/projects/${encodeURIComponent(project.id)}`); }
      catch (failure) { setError(message(failure)); setBusy(false); }
    }}>
      <label htmlFor="project-name" className="block font-display font-medium">Nombre del proyecto</label>
      <div className="flex flex-wrap gap-3">
        <input className={`${field} w-full sm:max-w-sm`} id="project-name" value={name} onChange={(event) => setName(event.target.value)} required />
        <Button type="submit" disabled={busy || !name.trim()}><Plus />{busy ? "Creando…" : "Crear proyecto"}</Button>
      </div>
      {error && <Problem>{error}</Problem>}
    </form>
    {loadError ? <div className="space-y-2"><Problem>{loadError}</Problem><Button variant="outline" onClick={() => { setLoadError(""); retry(attempt + 1); }}>Reintentar</Button></div> :
      !list ? <div role="status"><span className="sr-only">Cargando proyectos…</span><Skeleton className="h-28 w-full" /></div> :
      !list.length ? <p className={`${panel} text-muted-foreground`}>Todavía no hay proyectos. Crea uno para empezar.</p> :
      <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{list.map((project) => <li key={project.id}>
        <Link href={`/projects/${encodeURIComponent(project.id)}`} className={`${panel} block transition-colors hover:border-primary/50 focus-visible:outline-2 focus-visible:outline-ring`}>
          <div className="flex justify-between text-primary"><FolderKanban aria-hidden /><ArrowUpRight aria-hidden /></div>
          <h2 className="break-words font-display text-xl font-semibold">{project.name}</h2>
          <p className="font-mono text-xs text-muted-foreground">{project.assets} recursos · {project.tracks} pistas</p>
        </Link>
      </li>)}</ul>}
  </StudioPage>;
}

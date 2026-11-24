"use client";

import Link from "next/link";
import { HardDrive, History, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { field, message, panel, Problem, StudioPage } from "@/components/projects/studio-ui";
import { Button } from "@/components/ui/button";
import { ApiError, backups, projects, type BackupEvent, type BackupItem, type BackupPreview, type BackupSettings } from "@/lib/api";
import type { ProjectSummary } from "@/lib/timeline";

const number = new Intl.NumberFormat("es", { maximumFractionDigits: 2 });
const size = (n: number) => n >= 1024 ** 3 ? `${number.format(n / 1024 ** 3)} GiB`
  : n >= 1024 ** 2 ? `${number.format(n / 1024 ** 2)} MiB`
  : n >= 1024 ? `${number.format(n / 1024)} KiB` : `${number.format(n)} B`;
const date = (value: string) => new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString("es");
const verifications = { unchecked: "Hashes sin verificar", verified: "Hashes verificados", invalid: "Respaldo inválido" };
const outcomes = { ok: "Correcto", denied: "Rechazado", error: "Error" };

export function BackupView() {
  const [settings, setSettings] = useState<BackupSettings>();
  const [folder, setFolder] = useState("");
  const [projectList, setProjectList] = useState<ProjectSummary[]>([]);
  const [projectId, setProjectId] = useState("");
  const [includeAssets, setIncludeAssets] = useState(false);
  const [preview, setPreview] = useState<BackupPreview>();
  const [confirmed, setConfirmed] = useState(false);
  const [items, setItems] = useState<BackupItem[]>([]);
  const [history, setHistory] = useState<BackupEvent[]>([]);
  const [copy, setCopy] = useState<{ id: string; name: string }>();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [state, catalog] = await Promise.all([backups.settings(), projects.list()]);
        if (!active) return;
        setSettings(state);
        setFolder(state.location);
        setProjectList(catalog.items);
        const list = state.status === "ready" ? await backups.list() : { items: [] };
        const events = await backups.audit();
        if (active) { setItems(list.items); setHistory(events); }
      } catch (problem) {
        if (active) setError(message(problem));
      } finally {
        if (active) setBusy(false);
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  function clearPreview() { setPreview(undefined); setConfirmed(false); }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (problem) {
      setError(message(problem));
    } finally {
      try { setHistory(await backups.audit()); }
      catch (problem) { setError((previous) => previous || message(problem)); }
      setBusy(false);
    }
  }

  const ready = settings?.status === "ready";
  return <StudioPage>
    <header className="space-y-2">
      <p className="mono-label flex items-center gap-2"><HardDrive className="size-4 text-primary" aria-hidden /> Almacenamiento local</p>
      <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">Respaldo</h1>
      <p className="max-w-2xl text-sm text-muted-foreground">Guarda versiones de tus proyectos en una carpeta de este equipo y restáuralas como copias independientes.</p>
    </header>
    {error && <Problem>{error}</Problem>}
    <div role="status" aria-live="polite" className="space-y-2 text-sm">
      {busy && <p className="text-muted-foreground">Procesando…</p>}
      {notice && <p>{notice}</p>}
      {copy && <Link href={`/projects/${encodeURIComponent(copy.id)}`} className="text-primary underline">Abrir {copy.name}</Link>}
    </div>

    <div className="grid items-start gap-4 lg:grid-cols-2">
      <section className={panel} aria-labelledby="backup-location">
        <h2 id="backup-location" className="font-display text-lg font-semibold">Carpeta de destino</h2>
        <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); void run(async () => {
          const state = await backups.configure(folder.trim());
          setSettings(state);
          setFolder(state.location);
          clearPreview();
          setItems([]);
          setNotice("Carpeta de respaldo configurada.");
          setItems((await backups.list()).items);
        }); }}>
          <label className="grid gap-1.5 text-sm">Ruta absoluta
            <input value={folder} onChange={(event) => { setFolder(event.target.value); clearPreview(); }}
              disabled={busy} className={`${field} w-full font-mono`} aria-describedby="backup-path-help" required />
          </label>
          <p id="backup-path-help" className="text-xs text-muted-foreground">Elige una carpeta local fuera del repositorio y del workspace. Studio la creará si no existe.</p>
          <Button type="submit" variant="outline" disabled={busy || !folder.trim()} className="justify-self-start">Validar y guardar carpeta</Button>
        </form>
        {ready && <p className="break-all text-xs text-muted-foreground">Destino activo: <span className="font-mono">{settings.location}</span> · {size(settings.free_bytes ?? 0)} libres al consultar.</p>}
        {settings?.error && <Problem>{settings.error}</Problem>}
      </section>

      <section className={panel} aria-labelledby="backup-create">
        <h2 id="backup-create" className="font-display text-lg font-semibold">Nuevo respaldo</h2>
        <label className="grid gap-1.5 text-sm">Proyecto
          <select value={projectId} className={field} disabled={busy} onChange={(event) => { setProjectId(event.target.value); clearPreview(); }}>
            <option value="">Elige un proyecto</option>
            {projectList.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-0.5 accent-primary" checked={includeAssets} disabled={busy}
            onChange={(event) => { setIncludeAssets(event.target.checked); clearPreview(); }} /> Incluir archivos de los recursos del proyecto
        </label>
        <p className="text-xs text-muted-foreground">Por defecto solo se guardan el timeline y los metadatos. Los renders no se incluyen como archivos de trabajo.</p>
        <Button variant="outline" disabled={busy || !ready || !projectId} onClick={() => void run(async () => {
          clearPreview();
          setPreview(await backups.preview(projectId, includeAssets));
        })}>Generar vista previa</Button>
        {preview && <div className="space-y-3 rounded-xl border border-primary/30 bg-primary/5 p-3 text-sm">
          <h3 className="font-semibold">Contenido del respaldo</h3>
          <p className="break-all text-xs text-muted-foreground">{preview.location}</p>
          <p>{size(preview.total_bytes)} en total · {size(preview.free_bytes)} libres · {preview.include_assets ? "Opción de recursos activada" : "Sin archivos de recursos"}</p>
          <ul className="max-h-56 space-y-1 overflow-auto font-mono text-xs" aria-label="Archivos del respaldo">
            {preview.files.map((file) => <li key={file.name} className="flex justify-between gap-3">
              <span className="break-all">{file.name}{file.name !== file.label && ` · ${file.label}`}</span><span className="shrink-0">{size(file.size)}</span>
            </li>)}
          </ul>
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-0.5 accent-primary" checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} /> Confirmo guardar estos archivos en esta carpeta
          </label>
          <Button disabled={busy || !confirmed} onClick={() => void run(async () => {
            clearPreview();
            const item = await backups.create(projectId, preview);
            setIncludeAssets(false);
            setItems((current) => [item, ...current]);
            setNotice("Respaldo creado y hashes comprobados.");
          })}>Crear respaldo</Button>
        </div>}
      </section>
    </div>

    <section className={panel} aria-labelledby="backup-list">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="backup-list" className="flex items-center gap-2 font-display text-lg font-semibold"><ShieldCheck className="size-4 text-primary" aria-hidden /> Respaldos disponibles</h2>
        <Button variant="ghost" disabled={busy || !ready} onClick={() => void run(async () => setItems((await backups.list()).items))}>Actualizar lista</Button>
      </div>
      {!items.length && <p className="text-sm text-muted-foreground">{ready ? "No hay respaldos en esta carpeta." : "Configura una carpeta para consultar los respaldos."}</p>}
      <ul className="space-y-2">
        {items.map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 p-3">
          <div className="min-w-0 space-y-1">
            <p className="break-all text-sm font-medium">{item.project_name ?? item.id}</p>
            <p className="text-xs text-muted-foreground">{item.created_at && `${date(item.created_at)} · `}{item.total_bytes !== undefined && `${size(item.total_bytes)} · `}{item.assets !== undefined && `${item.assets} archivos de recursos · `}{verifications[item.verification]}</p>
            {item.error && <p className="text-xs text-destructive">{item.error}</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" disabled={busy} onClick={() => void run(async () => {
              try {
                const checked = await backups.verify(item.id);
                setItems((current) => current.map((row) => row.id === item.id ? checked : row));
              } catch (problem) {
                if (problem instanceof ApiError && [404, 422].includes(problem.status)) {
                  setItems((current) => current.map((row) => row.id === item.id ? { ...row, verification: "invalid", error: message(problem) } : row));
                }
                throw problem;
              }
            })}>Verificar hashes</Button>
            <Button size="sm" disabled={busy || item.verification === "invalid"} onClick={() => void run(async () => {
              setCopy(undefined);
              try {
                setCopy(await backups.restore(item.id));
              } catch (problem) {
                if (problem instanceof ApiError && problem.code === "BACKUP_HASH_MISMATCH") {
                  setItems((current) => current.map((row) => row.id === item.id ? { ...row, verification: "invalid", error: message(problem) } : row));
                }
                throw problem;
              }
              setItems((current) => current.map((row) => row.id === item.id ? { ...row, verification: "verified", error: undefined } : row));
              setProjectList((await projects.list()).items);
              setNotice("Copia restaurada. El proyecto original no se modificó.");
            })}>Restaurar como copia</Button>
          </div>
        </li>)}
      </ul>
    </section>

    <section className={panel} aria-labelledby="backup-history">
      <h2 id="backup-history" className="flex items-center gap-2 font-display text-lg font-semibold"><History className="size-4 text-primary" aria-hidden /> Historial de operaciones</h2>
      {!history.length && <p className="text-sm text-muted-foreground">Aún no hay operaciones registradas.</p>}
      <ol className="max-h-80 divide-y divide-white/10 overflow-auto">
        {history.map((event) => <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-xs" key={event.id}>
          <time dateTime={event.created_at} className="text-muted-foreground">{date(event.created_at)}</time>
          <span className="capitalize">{event.action}</span><span>{outcomes[event.status]}</span>
          <span className="break-all font-mono text-muted-foreground">{event.detail}</span>
        </li>)}
      </ol>
    </section>
  </StudioPage>;
}

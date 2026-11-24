"use client";

import { ArrowLeft, Redo2, Save, Undo2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { projects } from "@/lib/api";
import { emptyTrack, end, historyStep, initialHistory, items, labels, seconds, transform, withItems,
  type Asset, type Item, type Kind, type Project, type Timeline, type Track } from "@/lib/timeline";
import { ExportPanel, ProjectJobs } from "./project-output";
import { AIAssistant } from "./ai-assistant";
import { field, message, panel, Problem, StudioPage } from "./studio-ui";
import { TimelineBoard } from "./timeline-board";

const timelineOf = ({ tracks, transitions }: Timeline) => ({ tracks, transitions });

export function ProjectEditor({ id }: { id: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    projects.get(id).then((data) => { if (active) setProject(data); }, (failure) => { if (active) setLoadError(message(failure)); });
    return () => { active = false; };
  }, [id, retry]);
  return <StudioPage>
    <Link href="/projects" className="inline-flex items-center gap-2 rounded text-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"><ArrowLeft className="size-4" /> Proyectos</Link>
    {project ? <Editor initial={project} /> : loadError ? <><Problem>{loadError}</Problem><Button onClick={() => { setLoadError(""); setRetry(retry + 1); }}>Reintentar</Button></> : <p className={panel} role="status">Cargando proyecto…</p>}
  </StudioPage>;
}

function Editor({ initial }: { initial: Project }) {
  const { id } = initial;
  const [assets, setAssets] = useState(initial.assets);
  const [scriptPlan, setScriptPlan] = useState(typeof initial.metadata?.script_plan === "string" ? initial.metadata.script_plan : "");
  const [history, setHistory] = useState(() => initialHistory(timelineOf(initial)));
  const [saved, setSaved] = useState(() => JSON.stringify(timelineOf(initial)));
  const [version, setVersion] = useState(0);
  const [jobsVersion, setJobsVersion] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [editError, setEditError] = useState("");
  const [saveError, setSaveError] = useState(false);
  const [importError, setImportError] = useState("");
  const timeline = history.current;
  const dirty = JSON.stringify(timeline) !== saved;
  const track = timeline.tracks.find((candidate) => items(candidate).some((item) => item.id === selected));
  const clip = track && items(track).find((item) => item.id === selected);
  const title = (item: Item) => item.text ?? item.name ?? assets.find((asset) => asset.id === item.asset_id)?.name ?? item.id;

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function task(action: () => Promise<void>, onError: (error: unknown) => void) {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    try { await action(); return true; }
    catch (error) { onError(error); return false; }
    finally { lock.current = false; setBusy(false); }
  }
  function edit(next: Timeline | "undo" | "redo", nextSelection?: string) {
    const candidate = historyStep(history, next);
    if (candidate === history || JSON.stringify(candidate.current) === JSON.stringify(timeline)) return Promise.resolve(false);
    return task(async () => {
      setEditError("");
      const current = await projects.validate(id, candidate.current);
      setHistory({ ...candidate, current });
      if (nextSelection) setSelected(nextSelection);
      setSaveError(false);
    }, (error) => setEditError(message(error)));
  }
  function save() {
    if (!dirty && !saveError) return;
    void task(async () => {
      setEditError("");
      const result = await projects.save(id, timeline);
      const current = timelineOf(result);
      setSaved(JSON.stringify(current));
      setHistory({ ...history, current });
      setAssets(result.assets);
      setSaveError(false);
      setVersion((value) => value + 1);
    }, (error) => { setSaveError(true); setEditError(message(error)); });
  }
  function replace(target: Track, next: Item) {
    if (target.locked) return;
    edit({ ...timeline, tracks: timeline.tracks.map((entry) => entry.id === target.id ?
      withItems(entry, items(entry).map((item) => item.id === next.id ? next : item)) : entry) }, next.id);
  }
  function remove(clipId = selected) {
    const owner = timeline.tracks.find((entry) => items(entry).some((item) => item.id === clipId));
    if (!owner || owner.locked) return;
    edit({ ...timeline, tracks: timeline.tracks.map((entry) => entry.id === owner.id ?
      withItems(entry, items(entry).filter((item) => item.id !== clipId)) : entry) });
  }
  function add(kind: Kind, asset?: Asset) {
    const target = timeline.tracks.find((entry) => entry.id === (asset ? targets[asset.id] : targets.subtitle) && entry.kind === kind && !entry.locked) ??
      timeline.tracks.find((entry) => entry.kind === kind && !entry.locked);
    const item: Item = { id: crypto.randomUUID(), start_seconds: seconds(target ? Math.max(0, ...items(target).map(end)) : 0),
      duration_seconds: asset ? asset.duration_seconds : 1,
      ...(asset ? { asset_id: asset.id, source_in_seconds: 0 } : { text: "Nuevo subtítulo" }) };
    edit({ ...timeline, tracks: target ? timeline.tracks.map((entry) => entry.id === target.id ? withItems(entry, [...items(entry), item]) : entry) :
      [...timeline.tracks, withItems(emptyTrack(kind, crypto.randomUUID()), [item])] }, item.id);
  }
  function trackPicker(key: string, kind: Kind, title: string) {
    const options = timeline.tracks.filter((entry) => entry.kind === kind && !entry.locked);
    return options.length > 1 && <select aria-label={`Pista para ${title}`} className={field} value={options.some((option) => option.id === targets[key]) ? targets[key] : options[0].id}
      onChange={(event) => setTargets({ ...targets, [key]: event.target.value })}>{options.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}</select>;
  }

  return <div className="space-y-5" onKeyDown={(event) => {
    const typing = event.target instanceof HTMLElement && Boolean(event.target.closest("input, textarea, select, [contenteditable]"));
    const key = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && key === "s") { event.preventDefault(); save(); }
    if (busy || typing) return;
    if ((event.ctrlKey || event.metaKey) && ["z", "y"].includes(key)) { event.preventDefault(); edit(key === "y" || event.shiftKey ? "redo" : "undo"); }
    const clipButton = event.target instanceof HTMLElement ? event.target.closest<HTMLElement>("[data-clip]") : null;
    if (key === "delete" && clipButton?.dataset.clip) { event.preventDefault(); remove(clipButton.dataset.clip); }
  }}>
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0"><p className="mono-label text-primary">Estudio / montaje local</p><h1 className="mt-2 break-words font-display text-4xl font-semibold tracking-tight">{initial.name}</h1></div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground" role="status">{saveError ? "Error de guardado" : busy ? "Procesando…" : dirty ? "Cambios sin guardar" : "Guardado"}</span>
        <Button size="icon" variant="outline" aria-label="Deshacer" disabled={busy || !history.past.length} onClick={() => edit("undo")}><Undo2 /></Button>
        <Button size="icon" variant="outline" aria-label="Rehacer" disabled={busy || !history.future.length} onClick={() => edit("redo")}><Redo2 /></Button>
        <Button disabled={busy || (!dirty && !saveError)} onClick={save}><Save /> Guardar timeline</Button>
      </div>
    </header>
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(215px,270px)_minmax(0,1fr)]">
      <section className={panel} aria-labelledby="assets-heading">
        <h2 id="assets-heading" className="font-display text-lg font-semibold">Recursos</h2>
        <form className="space-y-2" onSubmit={(event) => {
          event.preventDefault();
          void task(async () => {
            setImportError("");
            const { asset } = await projects.import(id, path.trim());
            setAssets((previous) => [...previous, asset]);
            setPath(""); setVersion((value) => value + 1);
          }, (error) => setImportError(message(error)));
        }}>
          <label htmlFor="media-path" className="block text-sm">Ruta local</label>
          <input id="media-path" className={`${field} w-full`} value={path} onChange={(event) => setPath(event.target.value)} required aria-describedby="workspace-hint" />
          <p id="workspace-hint" className="text-xs text-muted-foreground">Solo archivos dentro de GHS_WORKSPACE_DIR.</p>
          <Button variant="outline" type="submit" disabled={busy || !path.trim()}>Importar recurso</Button>
        </form>
        {importError && <Problem>{importError}</Problem>}
        {!assets.length ? <p className="text-sm text-muted-foreground">Aún no hay recursos importados.</p> : <ul className="space-y-2">{assets.map((asset) => <li key={asset.id} className="space-y-2 rounded-lg border border-white/10 bg-background/50 p-2.5">
          <p className="break-words text-sm font-medium">{asset.name}</p><p className="font-mono text-xs text-muted-foreground">{labels[asset.kind as Kind] ?? asset.kind} · {asset.duration_seconds} s</p>
          {(asset.kind === "video" || asset.kind === "audio") && <div className="flex flex-wrap gap-2">
            {trackPicker(asset.id, asset.kind, asset.name)}
            <Button size="sm" variant="secondary" aria-label={`Añadir ${asset.name} a ${labels[asset.kind]}`} disabled={busy} onClick={() => add(asset.kind as Kind, asset)}>+ Añadir a {labels[asset.kind]}</Button>
          </div>}
        </li>)}</ul>}
      </section>
      <section className={panel} aria-labelledby="timeline-heading">
        <TimelineBoard timeline={timeline} title={title} selected={selected} select={setSelected} change={replace} busy={busy} />
        {editError && <Problem>{editError}</Problem>}
        <div className="flex flex-wrap gap-2">{trackPicker("subtitle", "subtitle", "subtítulos")}<Button size="sm" variant="outline" disabled={busy} onClick={() => add("subtitle")}>Añadir subtítulo</Button></div>
        {clip && track ? <Inspector key={JSON.stringify(clip)} clip={clip} name={title(clip)} disabled={busy || Boolean(track.locked)} apply={(next) => replace(track, next)} remove={() => remove()} /> :
          <p className="text-sm text-muted-foreground">Selecciona un clip para editar sus tiempos.</p>}
      </section>
    </div>
    <AIAssistant plan={scriptPlan} editorBusy={busy} applyPlan={(text) => task(async () => {
      setEditError("");
      const result = await projects.saveScriptPlan(id, text);
      setScriptPlan(result.text);
    }, (error) => setEditError(message(error)))} applySubtitles={(cues) => {
      const newTrack: Track = { kind: "subtitle", id: crypto.randomUUID(), name: "Subtítulos · IA", cues };
      return edit({ ...timeline, tracks: [...timeline.tracks, newTrack] }, cues[0]?.id);
    }} />
    <ExportPanel id={id} dirty={dirty} version={version} onRender={() => setJobsVersion((value) => value + 1)} />
    <ProjectJobs id={id} version={jobsVersion} />
  </div>;
}

function Inspector({ clip, name, disabled, apply, remove }: { clip: Item; name: string; disabled: boolean; apply: (next: Item) => void; remove: () => void }) {
  const [start, setStart] = useState(String(clip.start_seconds));
  const [trimStart, setTrimStart] = useState("0");
  const [trimEnd, setTrimEnd] = useState("0");
  const [text, setText] = useState(clip.text ?? "");
  return <form className="space-y-3 rounded-xl border border-white/10 bg-background/35 p-3" onSubmit={(event) => {
    event.preventDefault();
    const next = transform(transform({ ...clip, start_seconds: Number(start) }, "start", Number(trimStart)), "end", -Number(trimEnd));
    apply({ ...next, ...(clip.text === undefined ? {} : { text }) });
    setStart(String(clip.start_seconds)); setTrimStart("0"); setTrimEnd("0"); setText(clip.text ?? "");
  }}>
    <h3 className="break-words text-sm font-semibold">Clip seleccionado · {name}</h3>
    <p className="font-mono text-xs text-muted-foreground">Duración {clip.duration_seconds} s{clip.source_in_seconds !== undefined && ` · Entrada de fuente ${clip.source_in_seconds} s`}</p>
    <fieldset disabled={disabled} className="grid gap-2 sm:grid-cols-3">
      <label className="grid gap-1 text-xs">Posición (s)<input type="number" step="any" required className={field} value={start} onChange={(event) => setStart(event.target.value)} /></label>
      <label className="grid gap-1 text-xs">Recortar inicio (s)<input type="number" step="any" required className={field} value={trimStart} onChange={(event) => setTrimStart(event.target.value)} /></label>
      <label className="grid gap-1 text-xs">Recortar fin (s)<input type="number" step="any" required className={field} value={trimEnd} onChange={(event) => setTrimEnd(event.target.value)} /></label>
      {clip.text !== undefined && <label className="grid gap-1 text-xs sm:col-span-3">Texto del subtítulo<textarea className={field} value={text} onChange={(event) => setText(event.target.value)} /></label>}
    </fieldset>
    <div className="flex flex-wrap gap-2"><Button type="submit" size="sm" disabled={disabled}>Aplicar edición</Button><Button type="button" size="sm" variant="outline" disabled={disabled} onClick={remove}>Borrar clip</Button></div>
  </form>;
}

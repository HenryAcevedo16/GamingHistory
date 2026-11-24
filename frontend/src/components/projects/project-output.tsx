"use client";

import { Clapperboard, Download, Radio, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { projects, type Job, type Preflight, type Target } from "@/lib/api";
import { message, panel, Problem } from "./studio-ui";

const editors = [
  { target: "ffmpeg", name: "FFmpeg", action: "Renderizar con FFmpeg", icon: Radio },
  { target: "resolve", name: "DaVinci Resolve", action: "Enviar a Resolve", icon: Send },
  { target: "capcut", name: "CapCut / VectCutAPI", action: "Generar borrador CapCut", icon: Clapperboard },
] as const;

function ExportNotes({ review }: { review: Preflight }) {
  return <>
    {review.warnings.map((warning) => <p key={warning} className="text-sm text-muted-foreground">{warning}</p>)}
    <div className="space-y-1 text-sm">
      <p className="font-medium">Elementos no exportables ({review.unsupported.length})</p>
      {!!review.unsupported.length && <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
        {review.unsupported.map((item, index) => <li key={`${item.path}-${index}`} className="break-words">{item.reason} <code className="text-xs">{item.path}</code></li>)}
      </ul>}
    </div>
  </>;
}

export function ExportPanel({ id, dirty, version, onRender }: { id: string; dirty: boolean; version: number; onRender: () => void }) {
  const [refresh, setRefresh] = useState(0);
  const [reports, setReports] = useState<Partial<Record<Target, { key: string; review?: Preflight; error?: string }>>>({});
  const [confirm, setConfirm] = useState<{ target: Target; review: Preflight } | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const key = `${version}:${refresh}`;
  useEffect(() => {
    let active = true;
    for (const { target } of editors) {
      projects.preflight(id, target).then(
        (review) => { if (active) setReports((previous) => ({ ...previous, [target]: { key, review } })); },
        (error) => { if (active) setReports((previous) => ({ ...previous, [target]: { key, error: message(error) } })); },
      );
    }
    return () => { active = false; };
  }, [id, key]);

  async function send() {
    if (!confirm || dirty || sending) return;
    setSending(true); setError(""); setFeedback("");
    const { target, review } = confirm;
    try {
      if (target === "ffmpeg") {
        const job = await projects.render(id, review.revision, `renders/${crypto.randomUUID()}.mp4`);
        setFeedback(`Render encolado · ${job.id}`); onRender();
      } else if (target === "resolve") {
        const result = await projects.resolve(id, review.revision);
        setFeedback(`Proyecto guardado en Resolve: ${result.name} · ${result.clips} clips.`);
      } else {
        const { draft } = await projects.draft(id, review.revision);
        setFeedback(`Borrador CapCut generado en ${draft.path}`);
      }
    } catch (failure) { setError(message(failure)); }
    finally { setSending(false); setConfirm(null); setRefresh((value) => value + 1); }
  }

  return <section aria-labelledby="export-heading" className={panel}>
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 id="export-heading" className="font-display text-lg font-semibold">Enviar a</h2>
      <Button variant="ghost" size="sm" disabled={sending} onClick={() => setRefresh((value) => value + 1)}>Actualizar disponibilidad</Button></div>
    <p className="text-sm text-muted-foreground">Flujo local. La revisión corresponde a la última versión guardada.</p>
    {dirty && <p role="status" className="text-sm text-amber-300">Guarda los cambios antes de enviar.</p>}
    {error && <Problem>{error}</Problem>}
    {feedback && <p role="status" className="break-all text-sm text-primary">{feedback}</p>}
    <div className="grid gap-3 xl:grid-cols-3">{editors.map(({ target, action, name, icon: Icon }) => {
      const report = reports[target]?.key === key ? reports[target] : undefined;
      const review = report?.review;
      return <article key={target} aria-label={name} className="flex min-w-0 flex-col items-start gap-2 rounded-xl border border-white/10 bg-background/45 p-3">
        <h3 className="flex items-center gap-2 font-semibold"><Icon aria-hidden className="size-4 text-primary" />{name}</h3>
        <p id={`${target}-availability`} className="break-words text-sm text-muted-foreground">{review?.reason ?? report?.error ?? "Comprobando disponibilidad…"}</p>
        {review && <>
          <p className="break-words font-mono text-[0.68rem] text-muted-foreground">Verificadas: {review.verified_capabilities.join(", ") || "ninguna"}</p>
          <ExportNotes review={review} />
        </>}
        <Button size="sm" className="mt-auto" aria-describedby={`${target}-availability`} disabled={!review?.available || dirty || sending}
          onClick={() => review && setConfirm({ target, review })}>{action}</Button>
      </article>;
    })}</div>
    <Dialog open={Boolean(confirm)} onOpenChange={(open) => { if (!open && !sending) setConfirm(null); }}>
      {confirm && <DialogContent showCloseButton={false} className="max-h-[85dvh] overflow-y-auto sm:max-w-lg motion-reduce:animate-none">
        <DialogTitle>{editors.find(({ target }) => target === confirm.target)?.action}</DialogTitle>
        <DialogDescription>Revisa lo que se omitirá antes de confirmar la operación local.</DialogDescription>
        <ExportNotes review={confirm.review} />
        <div className="flex flex-wrap justify-end gap-2">
          <DialogClose render={<Button variant="outline" disabled={sending} />}>Cancelar</DialogClose>
          <Button disabled={sending || dirty} onClick={() => void send()}>{sending ? "Enviando…" : "Confirmar envío"}</Button>
        </div>
      </DialogContent>}
    </Dialog>
  </section>;
}

const states = { queued: "En cola", running: "Ejecutando", done: "Completado", failed: "Fallido" };

export function ProjectJobs({ id, version }: { id: string; version: number }) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const { items } = await projects.jobs(id); if (active) { setJobs(items); setError(""); } }
      catch (failure) { if (active) setError(message(failure)); }
      finally { if (active) timer = setTimeout(poll, 2000); }
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [id, version]);

  return <section className={panel} aria-labelledby="jobs-heading">
    <h2 id="jobs-heading" className="font-display text-lg font-semibold">Trabajos del proyecto</h2>
    {error && <Problem>{error}</Problem>}
    {!jobs ? (!error && <p role="status" className="text-sm text-muted-foreground">Cargando trabajos…</p>) : !jobs.length ? <p className="text-sm text-muted-foreground">Aún no hay trabajos para este proyecto.</p> :
      <ul className="space-y-2">{jobs.map((job) => <li key={job.id} className="space-y-2 rounded-xl border border-white/10 bg-background/45 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{job.plugin_id} · {job.kind}</h3>
          <p role="status" className="font-mono text-xs text-primary">{states[job.status]} · {job.progress}% <span className="text-muted-foreground">({job.status})</span></p></div>
        <p className="break-all font-mono text-xs text-muted-foreground">{job.output_path}</p>
        {job.status === "done" && <a className="inline-flex items-center gap-2 rounded text-sm text-primary underline focus-visible:outline-2 focus-visible:outline-ring" href={projects.result(job.id)}><Download className="size-4" /> Descargar resultado</a>}
        {(job.log || job.error) && <details open={job.status === "failed" || undefined} className="text-sm"><summary className="cursor-pointer rounded focus-visible:outline-2 focus-visible:outline-ring">{job.error ? "Log de error" : "Log"}</summary>
          <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all font-mono text-xs text-muted-foreground">{[job.error, job.log].filter(Boolean).join("\n")}</pre></details>}
      </li>)}</ul>}
  </section>;
}

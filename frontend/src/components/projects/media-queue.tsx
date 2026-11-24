"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { projects, uploadMedia } from "@/lib/api";
import { labels, mediaLane, moveIndex, newLane, type Asset, type MediaLane, type Placement, type Track } from "@/lib/timeline";
import { field, message } from "./studio-ui";

type Row = { id: string; name: string; progress: number; status: "waiting" | "uploading" | "ready" | "error";
  file?: File; note: string; start: Placement["start"]; zeroTrack?: string; music?: boolean; asset?: Asset; error?: string };
type Props = {
  projectId: string; tracks: Track[]; busy: boolean;
  run: (action: () => Promise<void>, onError: (error: unknown) => void) => Promise<boolean>;
  imported: (asset: Asset) => void; sync: (assets: Asset[]) => void;
  place: (entries: Placement[], targets: Partial<Record<MediaLane, string>>) => Promise<boolean>;
};

export function MediaQueue({ projectId, tracks, busy, run, imported, sync, place }: Props) {
  const [rows, setRows] = useState<Row[]>([]);
  const [notice, setNotice] = useState("");
  const [targets, setTargets] = useState<Partial<Record<MediaLane, string>>>({});
  const [over, setOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const chooseButton = useRef<HTMLButtonElement>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const ready = rows.flatMap((row) => row.asset ? [{ ...row, asset: row.asset }] : []);
  const waiting = rows.filter((row) => row.file);
  const kinds = [...new Set(ready.filter((row) => row.start === "next").map((row) => mediaLane(row.asset)).filter((kind) => kind !== null))];
  const chosen = Object.fromEntries(kinds.map((kind) => {
    const options = tracks.filter((track) => track.kind === kind);
    const fallback = options.find((track) => !track.locked)?.id ?? (options.length ? "" : newLane);
    const current = targets[kind];
    return [kind, (current === newLane || options.some((track) => track.id === current && !track.locked)) ? current : fallback];
  })) as Partial<Record<MediaLane, string>>;

  const update = (id: string, change: Partial<Row>) => setRows((previous) =>
    previous.map((row) => row.id === id ? { ...row, ...change } : row));

  function select(files: File[]) {
    if (busy || controller.current || !files.length) return;
    const batch: Row[] = files.map((file) => ({ id: crypto.randomUUID(), file, name: file.name, status: "waiting",
      progress: 0, note: "", start: "next" }));
    setRows((previous) => [...previous, ...batch]);
    setNotice(`${batch.length} archivos seleccionados. Puedes escribir sus notas antes de subirlos.`);
  }

  function upload() {
    if (busy || controller.current || !waiting.length) return;
    const abort = new AbortController();
    controller.current = abort;
    setUploading(true);
    void run(async () => {
      let count = 0;
      for (const [index, row] of waiting.entries()) {
        if (abort.signal.aborted) {
          update(row.id, { file: undefined, status: "error", error: "No enviado: subida cancelada." });
          continue;
        }
        update(row.id, { status: "uploading" });
        setNotice(`Subiendo ${row.name} (${index + 1} de ${waiting.length}).`);
        try {
          const asset = await uploadMedia(projectId, row.file!, row.note, abort.signal,
            (progress) => update(row.id, { progress }));
          imported(asset);
          update(row.id, { file: undefined, status: "ready", asset });
          count++;
        } catch (error) {
          update(row.id, { file: undefined, status: "error", error: message(error) });
        }
      }
      if (abort.signal.aborted) {
        setNotice(`Subida detenida. ${count} de ${waiting.length} confirmados; los ya guardados siguen en Recursos.`);
        // A request that committed just before cancellation may have lost its response.
        try { sync((await projects.get(projectId)).assets); } catch { /* next open reloads the project */ }
      } else {
        setNotice(`${count} de ${waiting.length} importados. ${waiting.length - count} con error.`);
      }
    }, (error) => setNotice(message(error))).finally(() => { controller.current = null; setUploading(false); });
  }

  function move(index: number, direction: -1 | 1) {
    const next = moveIndex(rows, index, direction);
    if (busy || next === rows) return;
    setRows(next);
    setNotice(`${rows[index].name}: posición ${index + direction + 1} de ${rows.length}.`);
  }

  return <div className="space-y-3">
    <div className={`space-y-2 rounded-lg border border-dashed p-3 ${over ? "border-primary bg-primary/10" : "border-white/25"}`}
      onDragOver={(event) => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); setOver(!busy); } }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => { event.preventDefault(); setOver(false); select(Array.from(event.dataTransfer.files)); }}>
      <input ref={input} type="file" multiple className="hidden"
        accept=".mp4,.mov,.m4v,.m4a,.mkv,.webm,.avi,.mp3,.wav,.flac,.ogg,.opus,.png,.jpg,.jpeg,.webp,.bmp"
        onChange={(event) => { select(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
      <Button ref={chooseButton} type="button" disabled={busy} aria-describedby="upload-help" onClick={() => input.current?.click()}>Elegir archivos</Button>
      <p id="upload-help" className="text-xs text-muted-foreground">O suelta archivos aquí. Se copian al workspace sin modificar los originales.</p>
      {uploading && <Button size="sm" variant="outline" onClick={() => controller.current?.abort()}>Cancelar subida</Button>}
    </div>
    <p className="text-xs text-muted-foreground empty:sr-only" role="status">{notice}</p>
    {rows.length > 0 && <section className="space-y-2" aria-labelledby="queue-heading">
      <h3 id="queue-heading" className="text-sm font-semibold">Cola de importación</h3>
      <ol className="space-y-2">
        {rows.map((row, index) => {
          const kind = row.asset ? mediaLane(row.asset) : null;
          return <li key={row.id} className="space-y-1 rounded-lg border border-white/10 p-2">
          <p className="break-words text-sm">{index + 1}. {row.name}</p>
          {row.status === "uploading" && <progress aria-label={`Subida de ${row.name}`} max={100} value={row.progress} className="w-full accent-primary" />}
          <p className={row.status === "error" ? "text-xs text-red-300" : "text-xs text-muted-foreground"} role="status">
            {row.status === "waiting" ? "En espera" : row.status === "ready" ? "Listo para añadir" :
              row.status === "error" ? row.error : row.progress < 100 ? "Subiendo…" : "Verificando con ffprobe…"}
          </p>
          {row.status === "waiting" && <label className="grid gap-1 text-xs">Nota opcional para {row.name}
            <textarea rows={2} maxLength={500} disabled={busy} className={field} value={row.note}
              onChange={(event) => update(row.id, { note: event.target.value })} />
          </label>}
          {kind === "audio" && <label className="grid gap-1 text-xs">Uso de {row.name}
            <select className={field} value={row.music ? "music" : "voice"} disabled={busy} onChange={(event) => {
              const music = event.target.value === "music";
              update(row.id, { music, start: music ? "zero" : "next" });
            }}><option value="voice">Audio narrado / secuencial</option><option value="music">Música de fondo</option></select>
          </label>}
          {kind && <label className="grid gap-1 text-xs">Inicio de {row.name}
            <select className={field} value={row.start} disabled={busy}
              onChange={(event) => update(row.id, { start: event.target.value as Placement["start"] })}>
              <option value="next">Después del anterior</option><option value="zero">Empezar en 0</option>
            </select>
          </label>}
          {kind && row.start === "zero" && <label className="grid gap-1 text-xs">Pista para {row.name} en 0
            <select className={field} value={row.zeroTrack ?? newLane} disabled={busy}
              onChange={(event) => update(row.id, { zeroTrack: event.target.value })}>
              <option value={newLane}>Nueva pista</option>
              {tracks.filter((track) => track.kind === kind).map((track) =>
                <option key={track.id} value={track.id} disabled={track.locked}>{track.name}{track.locked ? " · bloqueada" : ""}</option>)}
            </select>
          </label>}
          <div className="flex flex-wrap gap-1">
            <Button size="sm" variant="outline" aria-label={`Subir ${row.name} en la cola`} aria-disabled={busy || index === 0}
              className="aria-disabled:opacity-50" onClick={() => move(index, -1)}>↑</Button>
            <Button size="sm" variant="outline" aria-label={`Bajar ${row.name} en la cola`} aria-disabled={busy || index === rows.length - 1}
              className="aria-disabled:opacity-50" onClick={() => move(index, 1)}>↓</Button>
            <Button size="sm" variant="ghost" aria-label={`Quitar ${row.name} de la cola`} disabled={busy}
              onClick={() => { setRows((previous) => previous.filter((entry) => entry.id !== row.id)); setNotice(`${row.name} se quitó de la cola.`); }}>Quitar</Button>
          </div>
        </li>; })}
      </ol>
      {waiting.length > 0 && !uploading && <Button size="sm" disabled={busy} onClick={upload}>Subir archivos</Button>}
      {kinds.map((kind) => <label key={kind} className="grid gap-1 text-xs">
        Pista de {labels[kind].toLowerCase()} para la cola
        <select className={field} value={chosen[kind]} disabled={busy}
          onChange={(event) => setTargets((previous) => ({ ...previous, [kind]: event.target.value }))}>
          {!chosen[kind] && <option value="" disabled>Elige una pista libre</option>}
          {tracks.filter((track) => track.kind === kind).map((track) =>
            <option key={track.id} value={track.id} disabled={track.locked}>{track.name}{track.locked ? " · bloqueada" : ""}</option>)}
          <option value={newLane}>Nueva pista de {labels[kind].toLowerCase()}</option>
        </select>
      </label>)}
      {ready.length > 0 && <p className="text-xs text-muted-foreground">Los clips secuenciales siguen el orden de la cola, en pistas compatibles. Los que empiezan en 0 no desplazan esa secuencia.</p>}
      <Button size="sm" disabled={busy || Boolean(waiting.length) || !ready.length || kinds.some((kind) => !chosen[kind])} onClick={async () => {
        if (await place(ready, chosen)) {
          const placed = new Set(ready.map((row) => row.id));
          setRows((previous) => previous.filter((row) => !placed.has(row.id)));
          setNotice(`${ready.length} clips añadidos. Guarda la timeline para conservar el orden.`);
          requestAnimationFrame(() => chooseButton.current?.focus());
        }
      }}>Añadir todos en este orden</Button>
    </section>}
  </div>;
}

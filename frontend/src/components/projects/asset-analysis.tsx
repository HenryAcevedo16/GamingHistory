"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ai, aiProviders, ApiError, type AIModelList, type AIProvider, type VisionPreview, type VisionResult } from "@/lib/api";
import { rememberOpenCodeModel, visionModelFromCatalog } from "@/lib/ai-model-selection";
import type { Asset } from "@/lib/timeline";
import { combinedNote, fitsNote, formatBytes, VISION_PROPOSAL_WARNING } from "@/lib/vision";
import { field, message, Problem } from "./studio-ui";

const MAX_SELECTION = 32;
type Props = {
  projectId: string;
  assets: Asset[];
  busy: boolean;
  saveNote: (assetId: string, note: string, onError: (error: unknown) => void) => Promise<Asset | undefined>;
};

const failure = (error: unknown) => error instanceof ApiError ? `${error.code}: ${error.message}` : message(error);

export function AssetAnalysis({ projectId, assets, busy, saveNote }: Props) {
  const images = assets.filter((asset) => asset.kind === "image");
  const hasImages = images.length > 0;
  const [selected, setSelected] = useState<string[]>([]);
  const [provider, setProvider] = useState<AIProvider>("claude");
  const [catalog, setCatalog] = useState<AIModelList | null>(null);
  const [model, setModel] = useState("");
  const [claudeModel, setClaudeModel] = useState<{ model: string | null } | null>(null);
  const [claudeLookupFailed, setClaudeLookupFailed] = useState(false);
  const [preview, setPreview] = useState<{ ids: string[]; data: VisionPreview } | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [pending, setPending] = useState<"models" | "preview" | "send" | null>(null);
  const [results, setResults] = useState<Record<string, VisionResult>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const abort = useRef<AbortController | null>(null);
  const sending = useRef(false);

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    if (!hasImages || provider !== "claude") return;
    let active = true;
    void ai.claudeModel().then(
      (value) => { if (active) setClaudeModel(value); },
      () => { if (active) setClaudeLookupFailed(true); },
    );
    return () => { active = false; };
  }, [hasImages, provider]);

  if (!hasImages) return null;

  const visionModels = catalog?.vision_models ?? [];
  const active = selected.filter((id) => images.some((asset) => asset.id === id));
  const reason = provider === "opencode"
    ? !catalog ? "Carga los modelos de OpenCode y elige uno con entrada de imagen."
      : !model ? "Elige un modelo con entrada de imagen para habilitar el análisis."
        : !visionModels.includes(model) ? "El modelo elegido no acepta imágenes." : ""
    : claudeLookupFailed ? "No se pudo comprobar el destino de Claude Code. Vuelve a seleccionarlo para reintentar."
      : claudeModel === null ? "Comprobando el destino de Claude Code…" : "";
  const canAnalyze = !busy && pending === null && !reason;
  const destination = provider === "claude"
    ? claudeModel === null ? "consultando…" : claudeModel.model ?? "modelo predeterminado de Claude Code"
    : model || "elige un modelo";

  async function loadModels() {
    setPending("models"); setError(""); setNotice("");
    try {
      const result = await ai.models();
      setCatalog(result);
      setModel(visionModelFromCatalog(result, model));
    } catch (problem) {
      setCatalog(null); setModel("");
      setError(failure(problem));
    } finally { setPending(null); }
  }

  async function openPreview(ids: string[]) {
    const chosen = [...new Set(ids)].filter((id) => images.some((asset) => asset.id === id));
    if (!chosen.length || chosen.length > MAX_SELECTION || !canAnalyze) return;
    const controller = new AbortController();
    abort.current = controller;
    setPending("preview"); setError(""); setNotice("");
    try {
      const data = await ai.visionPreview(projectId, chosen, controller.signal);
      if (data.errors.length) {
        setResults((previous) => ({ ...previous,
          ...Object.fromEntries(data.errors.map((entry) => [entry.asset_id, entry])) }));
        setNotice(`${data.errors.length} imágenes no se pudieron preparar y no se enviarán.`);
      }
      if (!data.images.length) return;
      setPreview({ ids: data.images.map((entry) => entry.asset_id), data });
      setDialogOpen(true);
    } catch (problem) {
      if (!controller.signal.aborted) setError(failure(problem));
    } finally {
      abort.current = null;
      setPending(null);
    }
  }

  function send() {
    const current = preview;
    if (!current || sending.current) return;
    sending.current = true;
    setDialogOpen(false);
    const controller = new AbortController();
    abort.current = controller;
    setPending("send"); setError(""); setNotice("");
    void (async () => {
      try {
        const result = await ai.vision(
          { provider, model: provider === "opencode" ? model : undefined },
          projectId, current.ids, controller.signal,
        );
        setResults((previous) => ({ ...previous, ...Object.fromEntries(result.results.map((entry) => [entry.asset_id, entry])) }));
        setDrafts((previous) => {
          const next = { ...previous };
          for (const entry of result.results) {
            if (entry.status === "ok" && entry.description) next[entry.asset_id] = entry.description;
            else delete next[entry.asset_id];
          }
          return next;
        });
        setSelected([]);
        const failed = result.results.filter((entry) => entry.status === "error").length;
        setNotice(failed
          ? `${result.results.length - failed} de ${result.results.length} imágenes descritas en ${result.batches} lote(s). ${failed} con error.`
          : `${result.results.length} imágenes descritas en ${result.batches} lote(s). Revisa las propuestas antes de aceptarlas.`);
      } catch (problem) {
        if (controller.signal.aborted) {
          setNotice("Análisis cancelado. No se enviarán más lotes ni se guardará ninguna descripción.");
        } else {
          setError(failure(problem));
        }
      } finally {
        abort.current = null;
        sending.current = false;
        setPreview(null);
        setPending(null);
      }
    })();
  }

  async function accept(asset: Asset, description: string, replace: boolean) {
    setError("");
    setStatus((previous) => ({ ...previous, [asset.id]: "" }));
    const text = replace ? description.trim() : combinedNote(asset.note, description);
    const saved = await saveNote(asset.id, text, (problem) => {
      setStatus((previous) => ({ ...previous, [asset.id]: failure(problem) }));
    });
    if (!saved) return;
    setDrafts((previous) => { const next = { ...previous }; delete next[asset.id]; return next; });
    setResults((previous) => { const next = { ...previous }; delete next[asset.id]; return next; });
    setStatus((previous) => ({ ...previous, [asset.id]: replace ? "Nota reemplazada." : "Nota guardada." }));
  }

  function discard(assetId: string) {
    setDrafts((previous) => { const next = { ...previous }; delete next[assetId]; return next; });
    setResults((previous) => { const next = { ...previous }; delete next[assetId]; return next; });
    setStatus((previous) => ({ ...previous, [assetId]: "Propuesta descartada." }));
  }

  return <section className="space-y-3 rounded-lg border border-white/10 bg-background/50 p-3" aria-labelledby="vision-heading">
    <h3 id="vision-heading" className="text-sm font-semibold">Análisis de imágenes con IA</h3>
    <p className="text-xs text-muted-foreground">
      Nada se analiza al importar. Solo se envían las imágenes que elijas, como copias JPEG reducidas de hasta 1024 px,
      sin EXIF ni GPS. Los originales no se modifican y la descripción no se guarda hasta que la aceptes.
    </p>
    <div className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-sm">Proveedor de IA
        <select className={field} value={provider} disabled={pending !== null}
          onChange={(event) => {
            setClaudeModel(null); setClaudeLookupFailed(false);
            setProvider(event.target.value as AIProvider); setError(""); setNotice("");
          }}>
          <option value="claude">Claude Code</option>
          <option value="opencode">OpenCode</option>
        </select>
      </label>
      {provider === "opencode" && <>
        <Button type="button" variant="outline" disabled={pending !== null} onClick={() => void loadModels()}>
          {catalog ? "Actualizar modelos" : "Cargar modelos"}
        </Button>
        {catalog && (visionModels.length ? <label className="grid max-w-full gap-1 text-sm">Modelo con imágenes
          <select className={`${field} max-w-full`} value={model} disabled={pending !== null}
            onChange={(event) => { setModel(event.target.value); rememberOpenCodeModel(event.target.value); setError(""); }}>
            <option value="" disabled>Elige un modelo con entrada de imagen</option>
            {visionModels.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </label> : <p className="text-xs text-red-300">Ningún modelo del catálogo acepta imágenes.</p>)}
      </>}
    </div>
    <p className="text-xs text-muted-foreground">Destino: <strong>{aiProviders[provider]} · {destination}</strong>. {reason}</p>
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="outline" disabled={pending !== null} onClick={() =>
        setSelected(active.length === Math.min(images.length, MAX_SELECTION)
          ? [] : images.slice(0, MAX_SELECTION).map((asset) => asset.id))}>
        {active.length === Math.min(images.length, MAX_SELECTION) ? "Quitar selección" :
          images.length > MAX_SELECTION ? "Seleccionar las primeras 32" : "Seleccionar todas"}
      </Button>
      <Button size="sm" variant="secondary" disabled={!canAnalyze || !active.length}
        onClick={() => void openPreview(active)}>Analizar seleccionadas</Button>
      {active.length > 0 && <span className="text-xs text-muted-foreground">{active.length} seleccionadas (máximo 32)</span>}
    </div>
    <ul className="space-y-2">
      {images.map((asset) => {
        const result = results[asset.id];
        const draft = drafts[asset.id];
        const tooLong = draft !== undefined && !fitsNote(asset.note, draft);
        return <li key={asset.id} className="space-y-2 rounded-lg border border-white/10 p-2">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 accent-primary" checked={active.includes(asset.id)}
              disabled={pending !== null || (!active.includes(asset.id) && active.length >= MAX_SELECTION)}
              aria-label={`Seleccionar ${asset.name} para analizar`}
              onChange={(event) => setSelected((previous) => event.target.checked
                ? [...new Set([...previous, asset.id])] : previous.filter((id) => id !== asset.id))} />
            <span className="break-words">{asset.name}</span>
          </label>
          <Button size="sm" variant="outline" disabled={!canAnalyze} onClick={() => void openPreview([asset.id])}>
            Analizar {asset.name}
          </Button>
          {result?.status === "error" && <p className="text-xs text-red-300" role="status">
            {result.code}: {result.message}
          </p>}
          {result?.status === "ok" && draft !== undefined && <div className="space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-2">
            <p className="text-xs">{VISION_PROPOSAL_WARNING}</p>
            <label className="grid gap-1 text-xs">Descripción propuesta para {asset.name}
              <textarea rows={4} maxLength={500} className={field} value={draft} disabled={pending !== null}
                onChange={(event) => {
                  const value = event.target.value;
                  setDrafts((previous) => ({ ...previous, [asset.id]: value }));
                  setStatus((previous) => ({ ...previous, [asset.id]: "" }));
                }} />
            </label>
            <p className="text-xs text-muted-foreground">{draft.length} / 500 caracteres. Puedes editarla antes de aceptarla.</p>
            {result.trimmed && <p className="text-xs text-amber-300" role="status">
              La descripción superó 500 caracteres y se recortó en una frase completa.
            </p>}
            {result.urls_removed > 0 && <p className="text-xs text-muted-foreground" role="status">
              Se ocultó {result.urls_removed === 1 ? "un enlace" : `${result.urls_removed} enlaces`} de la descripción.
            </p>}
            {asset.note && <p className="break-words text-xs text-muted-foreground">Nota actual: {asset.note}</p>}
            {tooLong && <p className="text-xs text-red-300">La nota actual y la descripción superan 500 caracteres. Recorta el texto antes de aceptar.</p>}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" disabled={busy || pending !== null || !draft.trim() || tooLong}
                onClick={() => void accept(asset, draft, false)}>
                {asset.note ? "Añadir a la nota" : "Aceptar y guardar nota"}
              </Button>
              {asset.note && <Button size="sm" variant="outline" disabled={busy || pending !== null || !draft.trim()}
                onClick={() => void accept(asset, draft, true)}>Reemplazar nota</Button>}
              <Button size="sm" variant="ghost" disabled={pending !== null} onClick={() => discard(asset.id)}>Descartar</Button>
            </div>
          </div>}
          <p className="text-xs" role="status">{status[asset.id] ?? ""}</p>
        </li>;
      })}
    </ul>
    {(pending === "send" || pending === "preview" || pending === "models") && <p className="text-sm text-muted-foreground" role="status">
      {pending === "models" ? "Cargando modelos…" :
        pending === "preview" ? "Preparando copias reducidas para calcular el tamaño…" :
          `Analizando ${preview?.ids.length ?? 0} imágenes en ${preview?.data.batches ?? 0} lote(s)…`}
    </p>}
    {pending === "send" && <Button size="sm" variant="outline" onClick={() => abort.current?.abort()}>Cancelar análisis</Button>}
    {notice && <p className="text-sm text-muted-foreground" role="status">{notice}</p>}
    {error && <Problem>{error}</Problem>}
    <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open && !sending.current) setPreview(null); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Enviar imágenes al proveedor de IA</DialogTitle>
          <DialogDescription>
            Proveedor: <strong>{aiProviders[provider]}</strong> · Modelo: <strong>{destination}</strong><br />
            Imágenes: <strong>{preview?.ids.length ?? 0}</strong> · Tamaño total reducido: <strong>{formatBytes(preview?.data.total_bytes ?? 0)}</strong>
            {(preview?.data.total_bytes ?? 0) >= 1024 && <> ({preview?.data.total_bytes.toLocaleString("es-ES")} bytes)</>} · Lotes: <strong>{preview?.data.batches ?? 0}</strong>
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm font-medium">Estas imágenes saldrán de este equipo hacia el proveedor elegido.</p>
        <p className="text-xs text-muted-foreground">Se envían copias JPEG de hasta 1024 px, sin EXIF ni GPS. Los originales no se modifican.</p>
        {!!preview?.data.errors.length && <p className="text-xs text-amber-300">
          {preview.data.errors.length} imágenes no se pudieron preparar y no se enviarán.
        </p>}
        <DialogFooter>
          <Button variant="outline" onClick={() => { setDialogOpen(false); setPreview(null); }}>Cancelar</Button>
          <Button onClick={send}>Enviar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </section>;
}

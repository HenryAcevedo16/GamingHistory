"use client";

import { useState, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { ai, aiProviders, ApiError, type AICue, type AIModelList, type AIProvider, type SubtitleMode } from "@/lib/api";
import { field, message, panel, Problem } from "./studio-ui";

type Suggestion = { kind: "script"; text: string } | { kind: "subtitles"; text: string; cues: AICue[] };
const providerKey = "ghs.ai.provider";
const defaultProvider = (): AIProvider => "claude";
function readProvider(): AIProvider {
  try { return localStorage.getItem(providerKey) === "opencode" ? "opencode" : "claude"; }
  catch { return defaultProvider(); }
}
function subscribeProvider(change: () => void) {
  window.addEventListener("storage", change);
  return () => window.removeEventListener("storage", change);
}

export function AIAssistant({ projectId, plan, editorBusy, applyPlan, applySubtitles }: {
  projectId: string;
  plan: string;
  editorBusy: boolean;
  applyPlan: (text: string) => Promise<boolean>;
  applySubtitles: (cues: AICue[]) => Promise<boolean>;
}) {
  const [script, setScript] = useState("");
  const [srt, setSrt] = useState("");
  const [mode, setMode] = useState<SubtitleMode>("correct");
  const storedProvider = useSyncExternalStore(subscribeProvider, readProvider, defaultProvider);
  const [selectedProvider, setSelectedProvider] = useState<AIProvider | null>(null);
  const provider = selectedProvider ?? storedProvider;
  const [catalog, setCatalog] = useState<AIModelList | null>(null);
  const [model, setModel] = useState("");
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [pending, setPending] = useState<"generate" | "apply" | "models" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const canSend = provider === "claude" || Boolean(catalog && model);

  function changeProvider(value: AIProvider) {
    setSelectedProvider(value); setSuggestion(null); setError(""); setNotice("");
    try { localStorage.setItem(providerKey, value); } catch { /* Selection still works in memory. */ }
  }

  async function loadModels() {
    setPending("models"); setError(""); setNotice("");
    try {
      const result = await ai.models();
      setCatalog(result);
      setModel(result.models.includes(model) ? model : result.default_model ?? "");
    } catch (failure) {
      setCatalog(null); setModel("");
      setError(failure instanceof ApiError ? `${failure.code}: ${failure.message}` : message(failure));
    } finally { setPending(null); }
  }

  async function generate(kind: Suggestion["kind"]) {
    setPending("generate"); setSuggestion(null); setError(""); setNotice("");
    try {
      const selection = { provider, model: provider === "opencode" ? model : undefined };
      if (kind === "script") {
        const result = await ai.script(script, selection, projectId);
        setSuggestion({ kind, text: result.text });
      } else {
        const result = await ai.subtitles(srt, mode, selection, projectId);
        setSuggestion({ kind, text: result.srt, cues: result.cues });
      }
    } catch (failure) {
      setError(failure instanceof ApiError ? `${failure.code}: ${failure.message}` : message(failure));
    } finally { setPending(null); }
  }

  async function apply() {
    if (!suggestion) return;
    setPending("apply"); setError(""); setNotice("");
    try {
      const applied = suggestion.kind === "script" ? await applyPlan(suggestion.text) : await applySubtitles(suggestion.cues);
      if (!applied) {
        setError("No se aplicó la sugerencia. Revisa el aviso del editor e inténtalo de nuevo.");
        return;
      }
      setNotice(suggestion.kind === "script" ? "Plan guardado en el proyecto." : "Pista añadida. Usa Guardar timeline para conservarla.");
      setSuggestion(null);
    } finally { setPending(null); }
  }

  return <section className={panel} aria-labelledby="ai-editor-heading">
    <h2 id="ai-editor-heading" className="font-display text-lg font-semibold">Asistente de texto</h2>
    <div className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-sm">Proveedor de IA
        <select className={field} value={provider} disabled={Boolean(pending)}
          onChange={(event) => changeProvider(event.target.value as AIProvider)}>
          <option value="claude">Claude Code</option>
          <option value="opencode">OpenCode</option>
        </select>
      </label>
      {provider === "opencode" && <>
        <Button type="button" variant="outline" disabled={Boolean(pending)} onClick={() => void loadModels()}>
          {catalog ? "Actualizar modelos" : "Cargar modelos"}
        </Button>
        {catalog && <label className="grid max-w-full gap-1 text-sm">Modelo de OpenCode
          <select className={`${field} max-w-full`} value={model} disabled={Boolean(pending)}
            onChange={(event) => { setModel(event.target.value); setSuggestion(null); setError(""); setNotice(""); }}>
            <option value="" disabled>Elige un modelo</option>
            {catalog.models.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </label>}
      </>}
    </div>
    <p className="text-sm text-muted-foreground">
      {provider === "claude" ? "Cada envío comparte el texto de su campo con Anthropic." :
        "Cada envío comparte el texto de su campo con el servicio del modelo elegido a través de OpenCode local."}
      {" "}No pegues rutas, credenciales ni contenido de archivos .env.
      {provider === "opencode" && !catalog && " Carga los modelos para elegir uno y habilitar el envío."}
    </p>
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="min-w-0 space-y-2">
        <label htmlFor="ai-script" className="block text-sm">Texto de guion</label>
        <textarea id="ai-script" className={`${field} w-full`} rows={5} value={script} maxLength={12000} disabled={Boolean(pending)}
          onChange={(event) => { setScript(event.target.value); if (suggestion?.kind === "script") setSuggestion(null); }} />
        <p id="ai-plan-notes" className="text-xs text-muted-foreground">Al pedir un plan de guion y cortes, el proveedor recibe el nombre de archivo, tipo, duración y nota guardada de cada recurso. No se envían rutas ni archivos.</p>
        <Button type="button" variant="outline" aria-describedby="ai-plan-notes" disabled={editorBusy || !canSend || Boolean(pending) || !script.trim()} onClick={() => void generate("script")}>Enviar guion y sugerir estructura</Button>
      </div>
      <div className="min-w-0 space-y-2">
        <label htmlFor="ai-srt" className="block text-sm">Subtítulos o transcripción temporizada (SRT)</label>
        <p id="ai-srt-resources" className="text-xs text-muted-foreground">Subtítulos: se envían nombre de archivo, tipo y duración de los recursos, sin notas.</p>
        <textarea id="ai-srt" className={`${field} w-full font-mono`} rows={5} value={srt} maxLength={12000} disabled={Boolean(pending)}
          onChange={(event) => { setSrt(event.target.value); if (suggestion?.kind === "subtitles") setSuggestion(null); }} />
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Operación de subtítulos" className={field} value={mode} disabled={Boolean(pending)}
            onChange={(event) => { setMode(event.target.value as SubtitleMode); if (suggestion?.kind === "subtitles") setSuggestion(null); }}>
            <option value="correct">Corregir SRT</option>
            <option value="generate">Generar desde SRT</option>
          </select>
          <Button type="button" variant="outline" aria-describedby="ai-srt-resources" disabled={editorBusy || !canSend || Boolean(pending) || !srt.trim()} onClick={() => void generate("subtitles")}>Enviar SRT y sugerir subtítulos</Button>
        </div>
      </div>
    </div>
    {(pending || notice) && <p role="status" className="text-sm text-muted-foreground">{pending === "generate" ? `Esperando a ${aiProviders[provider]}…` : pending === "apply" ? "Aplicando…" : pending === "models" ? "Cargando modelos…" : notice}</p>}
    {error && <Problem>{error}</Problem>}
    {suggestion && <div className="space-y-2 rounded-lg border border-white/10 p-3">
      <h3 className="text-sm font-semibold">Vista previa · {suggestion.kind === "script" ? "plan de guion" : "subtítulos"}</h3>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-sm">{suggestion.text}</pre>
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={Boolean(pending) || editorBusy} onClick={() => void apply()}>
          {suggestion.kind === "script" ? (plan ? "Reemplazar plan guardado" : "Guardar como plan de guion") : "Añadir como nueva pista"}
        </Button>
        <Button type="button" variant="ghost" disabled={Boolean(pending)} onClick={() => setSuggestion(null)}>Descartar</Button>
      </div>
    </div>}
    {plan && <details className="space-y-2">
      <summary className="cursor-pointer text-sm font-semibold">Plan de guion guardado (no modifica los cortes)</summary>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-sm">{plan}</pre>
    </details>}
  </section>;
}

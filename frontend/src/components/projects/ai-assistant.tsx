"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ai, ApiError, type AICue, type SubtitleMode } from "@/lib/api";
import { field, message, panel, Problem } from "./studio-ui";

type Suggestion = { kind: "script"; text: string } | { kind: "subtitles"; text: string; cues: AICue[] };

export function AIAssistant({ plan, editorBusy, applyPlan, applySubtitles }: {
  plan: string;
  editorBusy: boolean;
  applyPlan: (text: string) => Promise<boolean>;
  applySubtitles: (cues: AICue[]) => Promise<boolean>;
}) {
  const [script, setScript] = useState("");
  const [srt, setSrt] = useState("");
  const [mode, setMode] = useState<SubtitleMode>("correct");
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [pending, setPending] = useState<"generate" | "apply" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function generate(kind: Suggestion["kind"]) {
    setPending("generate"); setSuggestion(null); setError(""); setNotice("");
    try {
      if (kind === "script") {
        const result = await ai.script(script);
        setSuggestion({ kind, text: result.text });
      } else {
        const result = await ai.subtitles(srt, mode);
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
    <h2 id="ai-editor-heading" className="font-display text-lg font-semibold">Asistente de texto · Claude Code</h2>
    <p className="text-sm text-muted-foreground">Cada botón de envío comparte solo el texto de su campo con Anthropic. No pegues rutas, credenciales ni contenido de archivos .env.</p>
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="min-w-0 space-y-2">
        <label htmlFor="ai-script" className="block text-sm">Texto de guion</label>
        <textarea id="ai-script" className={`${field} w-full`} rows={5} value={script} maxLength={12000} disabled={Boolean(pending)}
          onChange={(event) => { setScript(event.target.value); if (suggestion?.kind === "script") setSuggestion(null); }} />
        <Button type="button" variant="outline" disabled={Boolean(pending) || !script.trim()} onClick={() => void generate("script")}>Enviar guion y sugerir estructura</Button>
      </div>
      <div className="min-w-0 space-y-2">
        <label htmlFor="ai-srt" className="block text-sm">Subtítulos o transcripción temporizada (SRT)</label>
        <textarea id="ai-srt" className={`${field} w-full font-mono`} rows={5} value={srt} maxLength={12000} disabled={Boolean(pending)}
          onChange={(event) => { setSrt(event.target.value); if (suggestion?.kind === "subtitles") setSuggestion(null); }} />
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Operación de subtítulos" className={field} value={mode} disabled={Boolean(pending)}
            onChange={(event) => { setMode(event.target.value as SubtitleMode); if (suggestion?.kind === "subtitles") setSuggestion(null); }}>
            <option value="correct">Corregir SRT</option>
            <option value="generate">Generar desde SRT</option>
          </select>
          <Button type="button" variant="outline" disabled={Boolean(pending) || !srt.trim()} onClick={() => void generate("subtitles")}>Enviar SRT y sugerir subtítulos</Button>
        </div>
      </div>
    </div>
    {(pending || notice) && <p role="status" className="text-sm text-muted-foreground">{pending === "generate" ? "Esperando a Claude…" : pending === "apply" ? "Aplicando…" : notice}</p>}
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

"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ai, aiProviders, ApiError, type AIModelList, type AIProvider, type AIStatus } from "@/lib/api";
import { modelFromCatalog, readOpenCodeModel, rememberOpenCodeModel } from "@/lib/ai-model-selection";

export function AIStatusPanel() {
  return <section className="space-y-3 rounded-2xl border border-white/10 bg-card/70 p-5" aria-labelledby="ai-status">
    <h2 id="ai-status" className="font-display text-lg font-semibold">Asistente de texto</h2>
    <p className="text-sm text-muted-foreground">Cada comprobación envía al proveedor elegido un mensaje de prueba fijo, sin datos de tus proyectos.</p>
    <div className="grid gap-4 sm:grid-cols-2">
      <ProviderStatus provider="claude" />
      <ProviderStatus provider="opencode" />
    </div>
  </section>;
}

function ProviderStatus({ provider }: { provider: AIProvider }) {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"models" | "verify" | null>(null);
  const [catalog, setCatalog] = useState<AIModelList | null>(null);
  const [model, setModel] = useState("");

  async function loadModels() {
    setBusy("models"); setError(""); setStatus(null);
    try {
      const result = await ai.models();
      setCatalog(result);
      setModel(modelFromCatalog(result, model));
    } catch (failure) {
      setCatalog(null); setModel("");
      setError(failure instanceof ApiError ? `${failure.code}: ${failure.message}` : "No se pudieron cargar los modelos.");
    } finally { setBusy(null); }
  }

  async function verify() {
    setError(""); setStatus(null);
    if (provider === "opencode" && !model) {
      if (catalog || readOpenCodeModel()) {
        setError(catalog ? "AI_MODEL_REQUIRED: Elige un modelo del catálogo antes de verificar." :
          "AI_MODEL_REQUIRED: Pulsa Cargar modelos para validar tu selección guardada.");
        return;
      }
    }
    setBusy("verify");
    try { setStatus(await ai.status(provider, provider === "opencode" ? model : undefined)); }
    catch (failure) { setError(failure instanceof ApiError ? `${failure.code}: ${failure.message}` : `No se pudo verificar ${aiProviders[provider]}.`); }
    finally { setBusy(null); }
  }

  const problem = error || (status && !status.ready ? `${status.code}: ${status.message}` : "");
  return <div className="space-y-2 rounded-lg border border-white/10 p-3">
    <h3 className="text-sm font-semibold">{aiProviders[provider]}</h3>
    <div className="flex flex-wrap items-end gap-2">
      {provider === "opencode" && <>
        <Button type="button" variant="outline" disabled={Boolean(busy)} onClick={() => void loadModels()}>
          {busy === "models" ? "Cargando modelos…" : "Cargar modelos"}
        </Button>
        {catalog && <label className="grid max-w-full gap-1 text-sm">Modelo de OpenCode
          <select className="max-w-full rounded border bg-background p-1" value={model} disabled={Boolean(busy)}
            onChange={(event) => {
              setModel(event.target.value); rememberOpenCodeModel(event.target.value); setStatus(null); setError("");
            }}>
            <option value="" disabled>Elige un modelo</option>
            {catalog.models.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </label>}
      </>}
      <Button type="button" variant="outline" disabled={Boolean(busy)} onClick={() => void verify()}
        aria-label={`Verificar conexión con ${aiProviders[provider]}`}>{busy === "verify" ? "Verificando…" : "Verificar conexión"}</Button>
    </div>
    {problem ? <p role="alert" className="break-words text-sm text-destructive">{problem}</p> :
      <p role="status" className="text-sm text-muted-foreground">{busy === "verify" ? "Comprobando la sesión y la respuesta…" : status ?
        `Disponible${status.ready && status.cli_version ? ` · v${status.cli_version}` : ""} · sin herramientas` : "Sin verificar en esta visita."}</p>}
  </div>;
}

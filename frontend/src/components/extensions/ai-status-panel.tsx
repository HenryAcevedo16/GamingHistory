"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ai, aiProviders, ApiError, type AIProvider, type AIStatus } from "@/lib/api";

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
  const [busy, setBusy] = useState(false);

  async function verify() {
    setBusy(true); setError(""); setStatus(null);
    try { setStatus(await ai.status(provider)); }
    catch (failure) { setError(failure instanceof ApiError ? `${failure.code}: ${failure.message}` : `No se pudo verificar ${aiProviders[provider]}.`); }
    finally { setBusy(false); }
  }

  const problem = error || (status && !status.ready ? `${status.code}: ${status.message}` : "");
  return <div className="space-y-2 rounded-lg border border-white/10 p-3">
    <h3 className="text-sm font-semibold">{aiProviders[provider]}</h3>
    <Button type="button" variant="outline" disabled={busy} onClick={() => void verify()}
      aria-label={`Verificar conexión con ${aiProviders[provider]}`}>{busy ? "Verificando…" : "Verificar conexión"}</Button>
    {problem ? <p role="alert" className="break-words text-sm text-destructive">{problem}</p> :
      <p role="status" className="text-sm text-muted-foreground">{busy ? "Comprobando la sesión y la respuesta…" : status ?
        `Disponible${status.ready && status.cli_version ? ` · v${status.cli_version}` : ""} · sin herramientas` : "Sin verificar en esta visita."}</p>}
  </div>;
}

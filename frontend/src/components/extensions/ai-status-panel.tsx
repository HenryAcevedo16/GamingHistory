"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ai, ApiError, type AIStatus } from "@/lib/api";

export function AIStatusPanel() {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function verify() {
    setBusy(true); setError(""); setStatus(null);
    try { setStatus(await ai.status()); }
    catch (failure) { setError(failure instanceof ApiError ? `${failure.code}: ${failure.message}` : "No se pudo verificar Claude Code."); }
    finally { setBusy(false); }
  }

  return <section className="space-y-3 rounded-2xl border border-white/10 bg-card/70 p-5" aria-labelledby="claude-status">
    <h2 id="claude-status" className="font-display text-lg font-semibold">Asistente de texto · Claude Code</h2>
    <p className="text-sm text-muted-foreground">Usa la sesión de Claude Code de esta PC. La comprobación envía a Anthropic un mensaje de prueba fijo, sin datos de tus proyectos.</p>
    <Button type="button" variant="outline" disabled={busy} onClick={() => void verify()}>{busy ? "Verificando…" : "Verificar conexión con Claude"}</Button>
    {error ? <p role="alert" className="break-words text-sm text-destructive">{error}</p> :
      <p role="status" className="text-sm text-muted-foreground">{busy ? "Comprobando la sesión y la respuesta…" : status ?
        `Disponible · Claude Code ${status.cli_version} · SDK importado · sesión activa · sin herramientas` : "Sin verificar en esta visita."}</p>}
  </section>;
}

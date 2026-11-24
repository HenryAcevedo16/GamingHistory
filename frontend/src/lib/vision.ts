export const VISION_NOTE_LIMIT = 500;

export const VISION_PROPOSAL_WARNING =
  "La descripción es una propuesta de la IA: revísala antes de aceptarla";

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["KB", "MB", "GB"];
  let value = bytes;
  let unit = -1;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = unit < 0 ? Math.round(value) : Number(value.toFixed(1));
  return `${rounded.toLocaleString("es-ES", { maximumFractionDigits: 1 })} ${unit < 0 ? "B" : units[unit]}`;
}

/** Añade la propuesta después de la nota existente, sin tocar su contenido. */
export function combinedNote(note: string | null | undefined, description: string): string {
  const base = (note ?? "").trim();
  const proposal = description.trim();
  return base ? `${base}\n${proposal}` : proposal;
}

export function fitsNote(note: string | null | undefined, description: string): boolean {
  return combinedNote(note, description).length <= VISION_NOTE_LIMIT;
}

import type { AIModelList } from "./api";

const modelKey = "ghs.ai.opencode.model";

export function readOpenCodeModel(): string {
  try { return localStorage.getItem(modelKey) ?? ""; }
  catch { return ""; }
}

export function rememberOpenCodeModel(model: string) {
  try { localStorage.setItem(modelKey, model); }
  catch { /* The selection is still available in memory. */ }
}

export function modelFromCatalog(catalog: AIModelList, current: string): string {
  const wanted = current || readOpenCodeModel() || catalog.default_model;
  // Never silently replace a remembered model that has disappeared.
  return wanted && catalog.models.includes(wanted) ? wanted : "";
}

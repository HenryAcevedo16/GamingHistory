import type {
  ActionResponse,
  DiagnosticResponse,
  HealthResponse,
  PluginListResponse,
  PluginView,
  RequirementReport,
  RouterDecisionsResponse,
} from "@/lib/types";
import type { Asset, Project, ProjectSummary, Timeline } from "@/lib/timeline";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  code: string;
  details?: unknown;
  status: number;

  constructor(message: string, code: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api${path}`, {
      cache: "no-store",
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      `No se pudo contactar con el backend en ${API_BASE_URL}. ¿Está levantado?`,
      "NETWORK_ERROR",
      0,
    );
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const errorPayload = payload as
      | { error?: { code?: string; message?: string; details?: unknown }; detail?: { msg: string }[] }
      | null;
    throw new ApiError(
      errorPayload?.error?.message ?? (Array.isArray(errorPayload?.detail) ? errorPayload.detail.map((issue) => issue.msg).join("; ") : `La petición falló con HTTP ${response.status}.`),
      errorPayload?.error?.code ?? "HTTP_ERROR",
      response.status,
      errorPayload?.error?.details,
    );
  }

  return payload as T;
}

export type Target = "ffmpeg" | "resolve" | "capcut";
export type Preflight = { revision: string; available: boolean; reason: string; verified_capabilities: string[];
  unsupported: { path: string; reason: string; element_id?: string }[]; warnings: string[] };
export type Job = { id: string; project_id: string; kind: string; plugin_id: string; output_path: string;
  status: "queued" | "running" | "done" | "failed"; progress: number; log: string; error: string | null };
export type Draft = { id: string; path: string };
const json = (method: "POST" | "PUT", body: unknown) => ({ method, body: JSON.stringify(body) });
const path = (id: string) => `/projects/${encodeURIComponent(id)}`;

type UploadResult = { ok: true; asset: Asset } | { ok: false; error?: { code: string; message: string } };

export function uploadMedia(id: string, file: File, note: string, signal: AbortSignal, progress: (percent: number) => void): Promise<Asset> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new Error("Subida cancelada.")); return; }
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/api${path(id)}/assets/upload`);
    xhr.setRequestHeader("X-GHS-Upload", "1");
    xhr.responseType = "json";
    const abort = () => xhr.abort();
    signal.addEventListener("abort", abort, { once: true });
    xhr.onloadend = () => signal.removeEventListener("abort", abort);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) progress(Math.floor(event.loaded * 100 / event.total));
    };
    xhr.upload.onload = () => progress(100);
    xhr.onabort = () => reject(new Error("Subida cancelada."));
    xhr.onerror = () => reject(new Error("No se pudo contactar con el backend."));
    xhr.onload = () => {
      const body = xhr.response as UploadResult[] | { error?: { message: string } } | null;
      const result = Array.isArray(body) ? body[0] : null;
      if (xhr.status >= 200 && xhr.status < 300 && result?.ok && result.asset) resolve(result.asset);
      else reject(new Error((Array.isArray(body) ? result && !result.ok ? result.error?.message : undefined : body?.error?.message)
        ?? `No se pudo importar el archivo (HTTP ${xhr.status}).`));
    };
    const data = new FormData();
    data.append("files", file);
    if (note.trim()) data.append("note", note);
    xhr.send(data);
  });
}

export const aiProviders = { claude: "Claude Code", opencode: "OpenCode" } as const;
export type AIProvider = keyof typeof aiProviders;
export type AIStatus = { ready: true; cli_version?: string; tools_disabled: boolean } |
  { ready: false; code: string; message: string };
export type AIModelList = { models: string[]; default_model: string | null };
type AISelection = { provider: AIProvider; model?: string };
export type AICue = { id: string; start_seconds: number; duration_seconds: number; text: string };
export type SubtitleMode = "generate" | "correct";
const aiAction = { "X-GHS-AI-Action": "confirm" };
export const ai = {
  status: async (provider: AIProvider) => (await request<{ providers: Record<AIProvider, AIStatus> }>(
    `/ai/status?provider=${provider}`, { headers: aiAction })).providers[provider],
  models: () => request<AIModelList>("/ai/models", { headers: aiAction }),
  script: (text: string, selection: AISelection, projectId: string) => request<{ text: string }>("/ai/script", {
    ...json("POST", { text, ...selection, project_id: projectId, confirmed: true }), headers: aiAction,
  }),
  subtitles: (text: string, mode: SubtitleMode, selection: AISelection, projectId: string) => request<{ srt: string; cues: AICue[] }>("/ai/subtitles", {
    ...json("POST", { text, mode, ...selection, project_id: projectId, confirmed: true }), headers: aiAction,
  }),
};

export type BackupSettings = { status: "ready" | "not_configured" | "error"; location: string; free_bytes: number | null; error?: string };
export type BackupPreview = { location: string; free_bytes: number; total_bytes: number; revision: string;
  include_assets: boolean; files: { name: string; label: string; size: number }[] };
export type BackupItem = { id: string; verification: "unchecked" | "verified" | "invalid"; error?: string;
  project_name?: string; created_at?: string; total_bytes?: number; assets?: number };
export type BackupEvent = { id: number; action: string; status: "ok" | "denied" | "error"; detail: string; created_at: string };
const backupPath = (id: string) => `/backups/${encodeURIComponent(id)}`;

export const backups = {
  settings: () => request<BackupSettings>("/backups/settings"),
  configure: (folder: string) => request<BackupSettings>("/backups/settings", json("PUT", { folder })),
  preview: (project_id: string, include_assets: boolean) => request<BackupPreview>("/backups/preview", json("POST", { project_id, include_assets })),
  create: (project_id: string, preview: BackupPreview) => request<BackupItem>("/backups", json("POST", {
    project_id, include_assets: preview.include_assets, revision: preview.revision, confirmed: true,
  })),
  list: () => request<{ items: BackupItem[] }>("/backups"),
  verify: (id: string) => request<BackupItem>(`${backupPath(id)}/verify`, json("POST", {})),
  restore: (id: string) => request<{ id: string; name: string }>(`${backupPath(id)}/restore`, json("POST", {})),
  audit: () => request<BackupEvent[]>("/backups/audit"),
};

export const projects = {
  list: () => request<{ items: ProjectSummary[] }>("/projects"),
  create: (name: string) => request<Project>("/projects", json("POST", { name })),
  get: (id: string) => request<Project>(path(id)),
  saveScriptPlan: (id: string, text: string) => request<{ text: string }>(`${path(id)}/script-plan`, json("PUT", { text })),
  import: (id: string, file: string, note: string) => request<{ asset: Asset }>(`${path(id)}/media`, json("POST", { path: file, note })),
  saveNote: (id: string, assetId: string, note: string) =>
    request<Asset>(`${path(id)}/assets/${encodeURIComponent(assetId)}/note`, json("PUT", { note })),
  validate: (id: string, timeline: Timeline) => request<Timeline>(`${path(id)}/timeline/validate`, json("POST", timeline)),
  save: (id: string, timeline: Timeline) => request<Project>(`${path(id)}/timeline`, json("PUT", timeline)),
  preflight: (id: string, target: Target) => request<Preflight>(`${path(id)}/exports/${target}/preflight`),
  resolve: (id: string, revision: string) => request<{ name: string; timeline: string; clips: number }>(`${path(id)}/exports/resolve`, json("POST", { revision })),
  draft: (id: string, revision: string) => request<{ draft: Draft }>(`${path(id)}/drafts`, json("POST", { revision })),
  render: (id: string, revision: string, output_path: string) => request<Job>(`${path(id)}/renders/final`, json("POST", { revision, output_path })),
  jobs: (id: string) => request<{ items: Job[] }>(`/jobs?project_id=${encodeURIComponent(id)}`),
  result: (id: string) => `${API_BASE_URL}/api/jobs/${encodeURIComponent(id)}/result`,
};

function actionBody(confirmPermissions?: boolean): RequestInit {
  return {
    method: "POST",
    body:
      confirmPermissions === undefined
        ? undefined
        : JSON.stringify({ confirm_permissions: confirmPermissions }),
  };
}

export const api = {
  listPlugins: () => request<PluginListResponse>("/plugins"),
  getPlugin: (id: string) => request<PluginView>(`/plugins/${id}`),
  install: (id: string, confirmPermissions: boolean) =>
    request<ActionResponse>(`/plugins/${id}/install`, actionBody(confirmPermissions)),
  connect: (id: string) =>
    request<ActionResponse>(`/plugins/${id}/connect`, actionBody()),
  disconnect: (id: string) =>
    request<ActionResponse>(`/plugins/${id}/disconnect`, actionBody()),
  enable: (id: string) => request<ActionResponse>(`/plugins/${id}/enable`, actionBody()),
  disable: (id: string) => request<ActionResponse>(`/plugins/${id}/disable`, actionBody()),
  diagnose: (id: string) =>
    request<DiagnosticResponse>(`/plugins/${id}/diagnose`, actionBody()),
  verifyRequirements: (id: string) =>
    request<RequirementReport>(`/plugins/${id}/verify-requirements`, actionBody()),
  routerDecisions: (cloudAuthorized: boolean) =>
    request<RouterDecisionsResponse>(
      `/router/decisions?cloud_authorized=${cloudAuthorized ? "true" : "false"}`,
    ),
  health: () => request<HealthResponse>("/health"),
};

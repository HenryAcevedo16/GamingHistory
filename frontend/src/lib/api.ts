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

export type AIStatus = { ready: boolean; cli_version: string; sdk_importable: boolean; session_active: boolean; tools_disabled: boolean };
export type AICue = { id: string; start_seconds: number; duration_seconds: number; text: string };
export type SubtitleMode = "generate" | "correct";
const aiAction = { "X-GHS-AI-Action": "confirm" };
export const ai = {
  status: () => request<AIStatus>("/ai/status", { headers: aiAction }),
  script: (text: string) => request<{ text: string }>("/ai/script", { ...json("POST", { text, confirmed: true }), headers: aiAction }),
  subtitles: (text: string, mode: SubtitleMode) => request<{ srt: string; cues: AICue[] }>("/ai/subtitles", {
    ...json("POST", { text, mode, confirmed: true }), headers: aiAction,
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
  import: (id: string, file: string) => request<{ asset: Asset }>(`${path(id)}/media`, json("POST", { path: file })),
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

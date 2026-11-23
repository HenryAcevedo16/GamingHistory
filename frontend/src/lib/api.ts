import type {
  ActionResponse,
  DiagnosticResponse,
  HealthResponse,
  PluginListResponse,
  PluginView,
  RequirementReport,
  RouterDecisionsResponse,
} from "@/lib/types";

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
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
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
      | { error?: { code?: string; message?: string; details?: unknown } }
      | null;
    throw new ApiError(
      errorPayload?.error?.message ?? `La petición falló con HTTP ${response.status}.`,
      errorPayload?.error?.code ?? "HTTP_ERROR",
      response.status,
      errorPayload?.error?.details,
    );
  }

  return payload as T;
}

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

import type { HealthResponse } from "../types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function defaultApiBase() {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) return configured;
  const tauriWindow = globalThis as typeof globalThis & { __TAURI_INTERNALS__?: unknown };
  if (tauriWindow.__TAURI_INTERNALS__ || location.protocol === "tauri:") {
    return "http://127.0.0.1:8000";
  }
  const hostname = location.hostname || "127.0.0.1";
  return `${location.protocol || "http:"}//${hostname}:8000`;
}

const apiBase = defaultApiBase().replace(/\/$/, "");

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${apiBase}/api/v1/health/live`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new ApiError(
      "API健康检查失败",
      response.status,
      response.headers.get("X-Request-ID"),
    );
  }
  return (await response.json()) as HealthResponse;
}

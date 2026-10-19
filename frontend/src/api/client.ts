import type { ApiErrorBody, ApiErrorDetail } from "./types";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

/** Every failed request becomes an ApiError; components never see raw responses. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: ApiErrorDetail[];

  constructor(status: number, code: string, message: string, requestId: string | null = null, details: ApiErrorDetail[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorBody).error?.code === "string"
  );
}

async function send(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "Network request failed");
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON error (e.g. a proxy page): fall through to a generic error.
    }
    if (isErrorBody(body)) {
      const { code, message, request_id, details } = body.error;
      throw new ApiError(response.status, code, message, request_id, details ?? []);
    }
    throw new ApiError(response.status, "http_error", `Request failed (${response.status})`, response.headers.get("x-request-id"));
  }
  return response;
}

export async function apiRequest<T>(
  path: string,
  options: { method?: "GET" | "POST" | "PUT"; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const { method = "GET", body, signal } = options;
  const response = await send(path, {
    method,
    signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return (await response.json()) as T;
}

export async function apiDownload(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const response = await send(path, { method: "GET" });
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return { blob: await response.blob(), filename: match?.[1] ?? null };
}

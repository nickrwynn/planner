const isServer = typeof window === "undefined";
const API_BASE =
  (isServer ? process.env.API_INTERNAL_BASE_URL : undefined) ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

function getApiAuthMode(): "dev" | "bearer" {
  const mode = (
    isServer ? process.env.API_AUTH_MODE : process.env.NEXT_PUBLIC_API_AUTH_MODE
  )?.trim().toLowerCase();
  if (mode === "bearer") return "bearer";
  return "dev";
}

/**
 * Production auth: send JWT bearer token when configured.
 * Dev fallback: `X-User-Id` can still be used when API runs in AUTH_MODE=dev.
 */
export function getApiHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const authMode = getApiAuthMode();
  if (isServer) {
    const token = process.env.API_BEARER_TOKEN?.trim() || process.env.DEV_BEARER_TOKEN?.trim();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const id = process.env.DEV_USER_ID?.trim() || process.env.API_USER_ID?.trim();
    if (authMode === "dev" && id && !token) headers["X-User-Id"] = id;
  } else {
    const token =
      process.env.NEXT_PUBLIC_API_BEARER_TOKEN?.trim() || process.env.NEXT_PUBLIC_DEV_BEARER_TOKEN?.trim();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const id =
      process.env.NEXT_PUBLIC_DEV_USER_ID?.trim() || process.env.NEXT_PUBLIC_API_USER_ID?.trim();
    if (authMode === "dev" && id && !token) headers["X-User-Id"] = id;
  }
  return headers;
}

async function apiError(res: Response): Promise<Error> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = (await res.json()) as { detail?: string | { msg?: string }[] };
    if (typeof body?.detail === "string" && body.detail.trim()) {
      detail = body.detail;
    } else if (Array.isArray(body?.detail) && body.detail.length > 0) {
      const first = body.detail[0];
      if (first && typeof first.msg === "string" && first.msg.trim()) {
        detail = first.msg;
      }
    }
  } catch {
    // keep fallback
  }
  return new Error(detail);
}

export function toErrorMessage(e: unknown): string {
  if (e instanceof Error && e.message.trim()) return e.message;
  if (typeof e === "string" && e.trim()) return e;
  return "Request failed";
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", headers: getApiHeaders() });
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getApiHeaders() },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as T;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...getApiHeaders() },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as T;
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", headers: getApiHeaders() });
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as T;
}

/** Multipart upload: do not set Content-Type (browser sets boundary). Only attaches dev user header. */
export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: getApiHeaders(),
    body: form
  });
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as T;
}

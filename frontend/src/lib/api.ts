export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010/api/v1";

export const TOKEN_KEY = "token";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

// ---------------------------------------------------------------------------
// Session token storage
// ---------------------------------------------------------------------------

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ---------------------------------------------------------------------------
// Centralized 401 / session-expiry handling.
//
// Any authenticated request that returns 401 means the session has expired or
// is invalid. The session is cleared and the active page is redirected to the
// login screen (preserving the destination via the `next` query parameter).
// Redirects are de-duplicated so a burst of failing requests navigates once.
// ---------------------------------------------------------------------------

// Auth endpoints legitimately return 401 for wrong credentials / bad reset
// tokens; those are not session-expiry events.
const AUTH_FLOW_PATHS = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/forgot-password",
  "/auth/reset-password",
]);

type UnauthorizedHandler = (destination: string) => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;
let redirectScheduled = false;
const REDIRECT_COOLDOWN_MS = 300;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

function isExpiredToken(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]!.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" && payload.exp * 1000 <= Date.now();
  } catch {
    return false;
  }
}

export function handleUnauthorized(): void {
  clearStoredToken();
  if (typeof window === "undefined") return;
  if (window.location.pathname.startsWith("/login")) return;
  if (redirectScheduled) return;
  redirectScheduled = true;
  const destination = window.location.pathname + window.location.search;
  unauthorizedHandler?.(destination);
  window.setTimeout(() => {
    redirectScheduled = false;
  }, REDIRECT_COOLDOWN_MS);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  if (token && isExpiredToken(token)) {
    handleUnauthorized();
    throw new ApiError(401, "Session expired. Please log in again.");
  }
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    if (response.status === 401 && !AUTH_FLOW_PATHS.has(path)) handleUnauthorized();
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body.detail) detail = Array.isArray(body.detail) ? body.detail.map((d: { msg?: string }) => d.msg || "").join("; ") : String(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body ?? {}) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function downloadProject(projectId: number, format: string, fallbackName: string) {
  downloadFile(`/projects/${projectId}/export?format=${format}`, `${fallbackName}-blueprint.${format === "markdown" ? "md" : format}`);
}

export function downloadFile(path: string, filename: string) {
  const token = getStoredToken();
  fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
    .then((res) => {
      if (res.status === 401) {
        handleUnauthorized();
        throw new ApiError(401, "Session expired");
      }
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      return res.blob();
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    })
    .catch((err) => {
      if (!(err instanceof ApiError && err.status === 401)) {
        alert("Download failed. Make sure the blueprint has been generated.");
      }
    });
}

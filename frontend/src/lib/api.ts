/**
 * Typed API client.
 *
 * One place knows about the token, the error envelope and the base URL, so no
 * component has to think about any of it. The server's error shape is
 * `{error: {code, message, details}}`, which becomes an `ApiError` carrying the
 * code — components branch on the code, never on a message string.
 */
const BASE = "/api/v1";
const TOKEN_KEY = "parkspace.tokens";

export interface StoredTokens {
  access_token: string;
  refresh_token: string;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field-level messages from a 422, keyed by field name. */
  get fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    if (Array.isArray(this.details)) {
      for (const item of this.details as { loc?: (string | number)[]; msg?: string }[]) {
        const field = item.loc?.filter((p) => p !== "body").join(".");
        if (field && item.msg) out[field] = item.msg;
      }
    }
    return out;
  }
}

export function loadTokens(): StoredTokens | null {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch {
    return null;
  }
}

export function saveTokens(tokens: StoredTokens | null) {
  if (tokens) localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
  else localStorage.removeItem(TOKEN_KEY);
}

/** Fired when a refresh fails, so the app can send the user back to login. */
type AuthFailureHandler = () => void;
let onAuthFailure: AuthFailureHandler = () => {};
export function setAuthFailureHandler(handler: AuthFailureHandler) {
  onAuthFailure = handler;
}

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const tokens = loadTokens();
  if (!tokens?.refresh_token) return null;
  // Collapse parallel 401s into a single refresh call.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: tokens.refresh_token }),
        });
        if (!response.ok) {
          saveTokens(null);
          onAuthFailure();
          return null;
        }
        const data = (await response.json()) as StoredTokens;
        saveTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
        return data.access_token;
      } catch {
        return null;
      } finally {
        // Let the next 401 start a fresh attempt.
        setTimeout(() => (refreshInFlight = null), 0);
      }
    })();
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  formData?: FormData;
  signal?: AbortSignal;
  /** Internal: prevents a refresh loop. */
  retrying?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, formData, signal, retrying } = options;

  let url = `${BASE}${path}`;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = {};
  const token = loadTokens()?.access_token;
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined && !formData) headers["Content-Type"] = "application/json";

  const response = await fetch(url, {
    method,
    headers,
    body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
    signal,
  });

  if (response.status === 401 && !retrying && loadTokens()?.refresh_token) {
    const fresh = await refreshAccessToken();
    if (fresh) return request<T>(path, { ...options, retrying: true });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? safeParse(text) : null;

  if (!response.ok) {
    const envelope = (payload as { error?: { code?: string; message?: string; details?: unknown } })?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? "UNKNOWN",
      envelope?.message ?? response.statusText ?? "Something went wrong",
      envelope?.details,
    );
  }
  return payload as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  get: <T>(path: string, query?: RequestOptions["query"], signal?: AbortSignal) =>
    request<T>(path, { query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<T>(path, { method: "POST", formData });
  },
};

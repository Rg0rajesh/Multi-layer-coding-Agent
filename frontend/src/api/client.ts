
// Thin fetch wrapper — every page talks to the backend through this,
// not raw fetch(). Keeps auth headers, JSON handling, and token refresh
// in one place instead of copy-pasted into every hook.

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  full_name: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Access token lives here and nowhere else. The refresh token is an
// httpOnly cookie the browser already handles — we never touch it
// directly, which is the whole point of using a cookie for it.
let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

// Guards against the "three components 401 at the same time" case.
// Refresh tokens rotate on use, so firing three /auth/refresh calls
// back to back would burn the session the first call just issued.
let pendingRefresh: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!pendingRefresh) {
    pendingRefresh = fetch(`${API_BASE_URL}${API_PREFIX}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then(async (res) => {
        if (!res.ok) return null;
        const data: TokenResponse = await res.json();
        setAccessToken(data.access_token);
        return data.access_token;
      })
      .catch(() => null)
      .finally(() => {
        pendingRefresh = null;
      });
  }
  return pendingRefresh;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Skip attaching the bearer token — login/register/refresh itself */
  skipAuth?: boolean;
  /** Internal — stops a failed refresh from retrying forever */
  skipRetry?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth, skipRetry, headers, method, ...rest } = options;

  const res = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    ...rest,
    method: method ?? (body ? "POST" : "GET"),
    credentials: "include", // needed so the refresh cookie actually goes out
    headers: {
      "Content-Type": "application/json",
      ...(accessToken && !skipAuth ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // One retry, only once — a token that's still bad after a fresh
  // refresh means the user is genuinely logged out, not that we should
  // keep hammering /auth/refresh.
  if (res.status === 401 && !skipAuth && !skipRetry) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return request<T>(path, { ...options, skipRetry: true });
    }
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const isJson = (res.headers.get("content-type") ?? "").includes("application/json");
  const payload = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const detail = isJson && payload && typeof payload === "object" ? payload.detail : undefined;
    throw new ApiError(res.status, detail ? String(detail) : res.statusText, payload);
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "DELETE" }),
};

export { refreshAccessToken };
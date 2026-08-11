// js/api.js
//
// Direct fetch() wrapper — no build step, no Vite proxy. Every page talks
// to the backend through this file instead of calling fetch() by hand.
//
// Verified against the real backend on 2026-08-09 (see AUDIT.md):
//   POST /api/v1/auth/register  -> 201, sets refresh cookie, returns access_token
//   POST /api/v1/auth/login     -> 200, same shape
//   POST /api/v1/auth/refresh   -> 200, rotates the cookie, new access_token
//   POST /api/v1/auth/logout    -> 204, clears the cookie
//   GET  /api/v1/profile        -> 200 with Bearer token, 401 without

const API_BASE_URL = "http://localhost:8000";
const API_PREFIX = "/api/v1";

class ApiError extends Error {
  constructor(status, message, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// Kept in memory only, same as the React version — never localStorage.
// A hard refresh always re-derives it from the httpOnly refresh cookie.
let accessToken = null;

function setAccessToken(token) {
  accessToken = token;
}

function getAccessToken() {
  return accessToken;
}

let pendingRefresh = null;

async function refreshAccessToken() {
  if (!pendingRefresh) {
    pendingRefresh = fetch(`${API_BASE_URL}${API_PREFIX}/auth/refresh`, {
      method: "POST",
      credentials: "include", // sends the httpOnly agentx_refresh cookie
    })
      .then(async (res) => {
        if (!res.ok) return null;
        const data = await res.json();
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

async function request(path, options = {}) {
  const { body, skipAuth, skipRetry, headers, method, ...rest } = options;

  const res = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    ...rest,
    method: method || (body ? "POST" : "GET"),
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken && !skipAuth ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && !skipAuth && !skipRetry) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return request(path, { ...options, skipRetry: true });
    }
  }

  if (res.status === 204) {
    return undefined;
  }

  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const detail = isJson && payload && typeof payload === "object" ? payload.detail : undefined;
    throw new ApiError(res.status, detail ? String(detail) : res.statusText, payload);
  }

  return payload;
}

const api = {
  get: (path, options) => request(path, { ...options, method: "GET" }),
  post: (path, body, options) => request(path, { ...options, method: "POST", body }),
  patch: (path, body, options) => request(path, { ...options, method: "PATCH", body }),
  delete: (path, options) => request(path, { ...options, method: "DELETE" }),
};

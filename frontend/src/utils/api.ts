/**
 * 前端统一 API 客户端（Fetch 封装）
 * - 自动附带 Authorization 与 X-Workspace-Id 头
 * - 约定后端所有接口挂在 /api 前缀下
 */

const AUTH_TOKEN_KEY = "eduflow_token";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiErrorBody {
  error?: boolean;
  code?: string;
  message?: string;
  details?: unknown;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | null;

  constructor(status: number, body: ApiErrorBody | null, fallbackMessage?: string) {
    const msg =
      (body && (body.message as string)) ||
      (body && (body.detail as string)) ||
      fallbackMessage ||
      `请求失败 (${status})`;
    super(msg);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function getAuthToken(): string {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function getWorkspaceIdFromPath(pathname: string): string {
  const m = /^\/w\/([^/]+)\/?/.exec(pathname);
  if (m) {
    try {
      return decodeURIComponent(m[1]);
    } catch {
      return m[1];
    }
  }
  return "demo";
}

function encodeWorkspaceIdForHeader(id: string): string {
  if (!id) return "";
  try {
    return btoa(unescape(encodeURIComponent(id)));
  } catch {
    return /^[\x00-\x7f]*$/.test(id) ? id : "";
  }
}

export interface RequestOptions extends RequestInit {
  /** 相对 /api 的路径，例如 "/auth/login" */
  path: string;
}

export async function apiRequest<T = unknown>({
  path,
  method = "GET",
  headers,
  body,
  ...rest
}: RequestOptions & { method?: HttpMethod }): Promise<T> {
  const token = getAuthToken();
  const wid = getWorkspaceIdFromPath(window.location.pathname || "/");
  const encodedWid = encodeWorkspaceIdForHeader(wid);

  const mergedHeaders: HeadersInit = {
    ...(headers || {}),
  };

  if (token) {
    mergedHeaders["Authorization"] = `Bearer ${token}`;
  }
  if (encodedWid || wid) {
    mergedHeaders["X-Workspace-Id"] =
      encodedWid || (/^[\x00-\x7f]*$/.test(wid) ? wid : "");
  }

  const url = path.startsWith("/api")
    ? path
    : path.startsWith("/")
      ? `/api${path}`
      : `/api/${path}`;

  const resp = await fetch(url, {
    method,
    headers: mergedHeaders,
    body,
    ...rest,
  });

  const text = await resp.text();
  let json: ApiErrorBody | T | null = null;
  if (text) {
    try {
      json = JSON.parse(text) as ApiErrorBody | T;
    } catch {
      // 保留 text，便于调试
      json = { detail: text } as ApiErrorBody;
    }
  }

  if (!resp.ok) {
    throw new ApiError(resp.status, json as ApiErrorBody | null);
  }

  return json as T;
}

export function apiGet<T = unknown>(path: string): Promise<T> {
  return apiRequest<T>({ path, method: "GET" });
}

export function apiPostJson<T = unknown>(
  path: string,
  payload: unknown,
): Promise<T> {
  return apiRequest<T>({
    path,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}


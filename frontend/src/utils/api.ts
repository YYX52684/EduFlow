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

/** SSE 流式请求：POST JSON body，解析 event/data 行，回调 onProgress/onDone/onError */
export async function apiPostSSE(
  path: string,
  payload: unknown,
  callbacks: {
    onProgress?: (data: { percent?: number; message?: string; phase?: string }) => void;
    onDone?: (data: unknown) => void;
    onError?: (detail: string) => void;
  },
): Promise<void> {
  const token = getAuthToken();
  const wid = getWorkspaceIdFromPath(window.location.pathname || "/");
  const encodedWid = encodeWorkspaceIdForHeader(wid);

  const url = path.startsWith("/api")
    ? path
    : path.startsWith("/")
      ? `/api${path}`
      : `/api/${path}`;

  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(encodedWid || wid ? { "X-Workspace-Id": encodedWid || wid } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const text = await resp.text();
    let json: { detail?: string; message?: string } | null = null;
    try {
      json = JSON.parse(text);
    } catch {
      // ignore
    }
    const msg = json?.detail || json?.message || text || `请求失败 (${resp.status})`;
    callbacks.onError?.(msg);
    throw new ApiError(resp.status, json as ApiErrorBody | null, msg);
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    callbacks.onError?.("无响应体");
    return;
  }

  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop() || "";

    for (const chunk of chunks) {
      let event: string | null = null;
      let data: string | null = null;
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (!event || !data) continue;
      try {
        const d = JSON.parse(data) as Record<string, unknown>;
        if (event === "progress") {
          callbacks.onProgress?.(d as { percent?: number; message?: string; phase?: string });
        } else if (event === "done") {
          callbacks.onDone?.(d);
          return;
        } else if (event === "error") {
          callbacks.onError?.((d.detail as string) || data);
          return;
        }
      } catch (e) {
        if (event === "error") {
          callbacks.onError?.(data || "未知错误");
          return;
        }
        // 非 error 事件的 JSON 解析失败则忽略
      }
    }
  }
}


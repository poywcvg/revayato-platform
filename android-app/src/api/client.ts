/**
 * API client — a small ofetch-like wrapper over native fetch + AbortController.
 *
 * Mirrors the web app's `frontend/app/composables/useApi.ts` semantics:
 * - absolute base URL (no same-origin assumptions on native)
 * - Bearer token injected only when present; `/auth/*` never sends one
 * - 401 → single-flight refresh → replay once (seam reserved for the auth phase)
 * - normalized errors: `ApiError` distinguishes timeout vs network vs HTTP
 *
 * v1 is anonymous (browse + playback); the auth seam just needs this module
 * to stay token-aware.
 */
import {API_BASE_URL, HTTP_TIMEOUT_MS} from '../config';

export type RequestMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface RequestOptions {
  method?: RequestMethod;
  // Query params — null/undefined/empty-string values are dropped.
  query?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
  headers?: Record<string, string>;
  timeout?: number;
}

export class ApiError extends Error {
  readonly status: number;
  readonly isNetwork: boolean;
  readonly isTimeout: boolean;

  constructor(
    message: string,
    opts: {status?: number; isNetwork?: boolean; isTimeout?: boolean} = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status ?? 0;
    this.isNetwork = opts.isNetwork ?? false;
    this.isTimeout = opts.isTimeout ?? false;
  }
}

// Token store — v1 anonymous; kept module-scoped so the auth phase can wire
// AsyncStorage without touching any endpoint code.
const auth = {
  access: null as string | null,
  refresh: null as string | null,
};

let refreshInFlight: Promise<string | null> | null = null;

function buildQuery(params: RequestOptions['query']): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined || value === '') {continue;}
    search.set(key, String(value));
  }
  const q = search.toString();
  return q ? `?${q}` : '';
}

function errorFrom(status: number, body: unknown, fallback: string): ApiError {
  let text: string = fallback;
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const detail = (body as {detail?: unknown}).detail;
    if (typeof detail === 'string' && detail) {text = detail;}
  }
  return new ApiError(text, {status});
}

export function setTokens(access: string | null, refresh: string | null): void {
  auth.access = access;
  auth.refresh = refresh;
}

async function refreshTokens(): Promise<string | null> {
  if (!auth.refresh) {return null;}
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
          method: 'POST',
          headers: {Accept: 'application/json', 'Content-Type': 'application/json'},
          body: JSON.stringify({refresh: auth.refresh}),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          auth.access = null;
          return null;
        }
        auth.access = data.access ?? null;
        if (data.refresh) {auth.refresh = data.refresh;}
        return auth.access;
      } catch {
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const method = options.method ?? 'GET';
  const url = `${API_BASE_URL}${path}${buildQuery(options.query)}`;

  const timeoutMs = options.timeout ?? HTTP_TIMEOUT_MS.default;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.body !== undefined ? {'Content-Type': 'application/json'} : {}),
    ...options.headers,
  };
  // Never send credentials to auth endpoints (same rule as web execute()).
  if (auth.access && !path.startsWith('/auth/')) {
    headers.Authorization = `Bearer ${auth.access}`;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      signal: controller.signal,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (error) {
    const isAbort = error instanceof Error && error.name === 'AbortError';
    throw new ApiError('عدم پاسخگویی سرور', {
      isNetwork: true,
      isTimeout: isAbort,
    });
  } finally {
    clearTimeout(timer);
  }

  const raw = await res.text();
  let body: unknown = null;
  try {
    body = raw ? JSON.parse(raw) : null;
  } catch {
    body = raw;
  }

  if (res.status === 401 && !path.startsWith('/auth/') && auth.refresh) {
    const token = await refreshTokens();
    if (token) {
      return request<T>(path, options);
    }
  }

  if (!res.ok) {
    throw errorFrom(res.status, body, `درخواست ناموفق (${res.status})`);
  }

  return body as T;
}

export function get<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>(path, {...options, method: 'GET'});
}

/** GET with a short timeout tuned for the home rails endpoint. */
export function getRapid<T>(path: string, query?: RequestOptions['query']): Promise<T> {
  return request<T>(path, {method: 'GET', query, timeout: HTTP_TIMEOUT_MS.rails});
}

export function post<T>(
  path: string,
  body: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>(path, {...options, method: 'POST', body});
}

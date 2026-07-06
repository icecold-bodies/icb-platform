// lib/api.ts — shared fetch client for the MES SPA (WO v4.17, Phase 2C-1).
// Generalises the live/mock + credentialed-fetch pattern proven in CostingsContext
// so every context can reuse it. Same-origin in unified mode (FastAPI serves the
// build under /mes-app/); the Vite dev server proxies /api -> :8000. Override with
// VITE_API_BASE for split hosts.

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''
const TIMEOUT_MS = 10_000

// Session CSRF token (WO v4.18). The backend's csrf_middleware requires an
// X-CSRF-Token header on unsafe methods once a session exists. AppDataContext
// reads the token from GET /api/session and caches it here so apiPost/apiDelete
// send it. Left null in mock mode (mutations never reach the network there).
let _csrfToken: string | null = null
export function setCsrfToken(token: string | null): void {
  _csrfToken = token
}

/** Typed transport error. `status === 0` means network/timeout (→ mock fallback). */
export class ApiError extends Error {
  status: number
  detail?: string
  constructor(status: number, detail?: string) {
    super(detail || `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** FastAPI's `detail` is a STRING on HTTPException but an ARRAY OF OBJECTS on pydantic 422s.
 * ApiError.detail feeds toast messages (React children) directly, so a non-string here used to
 * crash the whole tree (minified React #31 → blank page). Normalize at the single chokepoint:
 * validation arrays become "field: message" lines; anything else non-string is stringified. */
function normalizeDetail(d: unknown): string | undefined {
  if (d === undefined || d === null) return undefined
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map((it) => {
      const o = it as { loc?: unknown; msg?: unknown }
      const loc = Array.isArray(o?.loc) ? o.loc.filter((p) => p !== 'body').join('.') : ''
      const msg = typeof o?.msg === 'string' ? o.msg : JSON.stringify(it)
      return loc ? `${loc}: ${msg}` : msg
    }).join('; ')
  }
  try { return JSON.stringify(d) } catch { return String(d) }
}

async function request<T>(path: string, init?: RequestInit, _csrfRetried = false): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  let res: Response
  const method = (init?.method ?? 'GET').toUpperCase()
  const csrfHeader: Record<string, string> =
    _csrfToken && method !== 'GET' && method !== 'HEAD' ? { 'X-CSRF-Token': _csrfToken } : {}
  try {
    res = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      signal: ctrl.signal,
      ...init,
      headers: { Accept: 'application/json', ...csrfHeader, ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'network') // aborted / offline
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) {
    let detail: string | undefined
    try {
      detail = normalizeDetail((await res.json())?.detail)
    } catch {
      /* non-JSON error body */
    }
    // v1.40.2 — CSRF self-heal: the SPA caches its token at page load, so a login in
    // another tab / the legacy iframe rotates the session and every mutation from this
    // (stale) page 403s with "CSRF token invalid" until a manual refresh. Instead:
    // refetch /api/session once (GET — no CSRF needed, cookie is current), adopt the
    // fresh token, and retry the original request a single time.
    if (res.status === 403 && !_csrfRetried && /csrf/i.test(detail ?? '')) {
      try {
        const s = await request<{ csrf_token?: string | null }>('/api/session', { method: 'GET' }, true)
        if (s?.csrf_token) {
          _csrfToken = s.csrf_token
          return request<T>(path, init, true)
        }
      } catch {
        /* fall through to the original 403 */
      }
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const apiGet = <T>(path: string): Promise<T> => request<T>(path, { method: 'GET' })

export const apiPost = <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

export const apiPatch = <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

export const apiPut = <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

export const apiDelete = <T>(path: string): Promise<T> => request<T>(path, { method: 'DELETE' })

/** Multipart upload (FormData). No Content-Type header → the browser sets the multipart boundary;
 *  request() still attaches credentials + the CSRF header (WO v4.28 — chassis photo upload). */
export const apiUpload = <T>(path: string, formData: FormData): Promise<T> =>
  request<T>(path, { method: 'POST', body: formData })

// v1.40.1 — mesAutoLogin() was removed. The demo autologin bypass is disabled in prod
// (and its route unmounted), and auth is now enforced by the server-side shell gate
// (/mes-app/* → /login when unauthenticated) plus <AuthGate>. Contexts read /api/session
// directly; a 401/403 there redirects to the server login (AppDataContext).

// ── Error → UX mapping (WO §3.2). Mutators call this in their catch block. ──────
export type ToastKind = 'error' | 'warn' | 'ok'
export type PushToast = (t: { kind: ToastKind; message: string }) => void

/** Map a thrown ApiError to the §3.2 treatment. 409 is RE-THROWN so the caller can
 *  show a blocking modal; everything else surfaces a toast (or a login redirect). */
export function handleApiError(err: unknown, pushToast: PushToast): void {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 401:
        window.location.href = `${API_BASE}/login`
        return
      case 403:
        pushToast({ kind: 'error', message: err.detail || "You don't have permission for that action." })
        return
      case 404:
        pushToast({ kind: 'warn', message: err.detail || 'That item no longer exists — refresh to update.' })
        return
      case 409:
        throw err // caller shows a blocking conflict modal
      case 422:
        pushToast({ kind: 'warn', message: err.detail || 'That action could not be completed.' })
        return
      default:
        pushToast({ kind: 'error', message: "Couldn't reach the server. Please try again." })
        return
    }
  }
  pushToast({ kind: 'error', message: 'Unexpected error.' })
}

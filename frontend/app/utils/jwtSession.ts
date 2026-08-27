/**
 * Access-token introspection used to keep a session alive silently.
 *
 * The access JWT lives about an hour; the session behind it lives for the full
 * 400-day refresh window. Reading `exp` locally lets the client rotate a new
 * access token *before* it dies, instead of discovering the problem when a
 * request comes back 401 — or worse, when a public endpoint quietly answers as
 * anonymous and the user simply looks logged out.
 */

/** Rotate this long before the token actually expires (clock skew + latency). */
export const ACCESS_TOKEN_REFRESH_SKEW_MS = 2 * 60 * 1000

function decodeBase64Url(segment: string) {
  const normalized = segment.replace(/-/g, '+').replace(/_/g, '/')
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=')
  try {
    if (typeof atob === 'function') return atob(padded)
    // Node's test runner (and any non-browser consumer) has no atob.
    return Buffer.from(padded, 'base64').toString('binary')
  } catch {
    return null
  }
}

/** Epoch milliseconds this access token expires at, or null when unreadable. */
export function accessTokenExpiresAt(token?: string | null): number | null {
  const payload = typeof token === 'string' ? token.split('.')[1] : null
  if (!payload) return null
  const decoded = decodeBase64Url(payload)
  if (!decoded) return null
  try {
    const claims = JSON.parse(decoded) as { exp?: unknown }
    return typeof claims.exp === 'number' && Number.isFinite(claims.exp) ? claims.exp * 1000 : null
  } catch {
    return null
  }
}

/**
 * True when the client should rotate a fresh access token before its next call.
 *
 * A missing token always needs one. A token whose `exp` cannot be read is left
 * alone on purpose: guessing "expired" there would fire a refresh on every
 * single request, so those fall back to the reactive 401 → refresh → retry path.
 */
export function accessTokenNeedsRefresh(
  token?: string | null,
  now: number = Date.now(),
  skewMs: number = ACCESS_TOKEN_REFRESH_SKEW_MS,
): boolean {
  if (!token) return true
  const expiresAt = accessTokenExpiresAt(token)
  if (expiresAt === null) return false
  return expiresAt - skewMs <= now
}

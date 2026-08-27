/**
 * The three cookies a session is made of, and who is allowed to write them.
 *
 * `refresh_token` is issued by the API through Set-Cookie and marked HttpOnly.
 * That is deliberate and load-bearing:
 *
 * - Safari's ITP caps any cookie written by JavaScript at seven days no matter
 *   what Max-Age it asks for. A refresh token written from the page therefore
 *   died after a week, and an iOS visitor who stayed away longer came back
 *   logged out with 393 days of session left. Cookies that arrive in a response
 *   header are not capped.
 * - Page scripts can no longer read the one credential that mints new sessions,
 *   so an XSS bug cannot walk off with a 400-day login.
 *
 * Because the page cannot read it, nothing here may try. The browser attaches it
 * to same-origin API calls on its own; a *server* render may still read it from
 * the incoming request header, which is why the ref below exists at all.
 */

/** Chromium's ceiling for persistent cookies; rotation renews the window. */
export const AUTH_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 400

export function useAuthCookies() {
  const shared = {
    path: '/',
    sameSite: 'lax' as const,
    secure: import.meta.env.PROD,
    maxAge: AUTH_SESSION_MAX_AGE_SECONDS,
  }

  /**
   * Readable by the page, and intentionally outliving its own `exp`.
   *
   * The JWT expires within the hour, but keeping the cookie lets the client read
   * that `exp` and rotate a replacement *before* sending a request. When the
   * cookie died with the token, authenticated calls to endpoints that also serve
   * guests silently answered as anonymous — which looks exactly like a logout.
   */
  const accessToken = useCookie<string | null>('access_token', shared)

  /**
   * Server-render read path for the HttpOnly refresh token.
   *
   * On the client this is always null and must not be written — the API owns it.
   * During SSR it reads the incoming Cookie header (HttpOnly hides cookies from
   * scripts, not from servers), so a render can rotate on the visitor's behalf
   * and pass the result on through Set-Cookie.
   */
  const refreshToken = useCookie<string | null>('refresh_token', { ...shared, httpOnly: true })

  /**
   * Credential-free marker that says "somebody is signed in here".
   *
   * The page cannot see the refresh token, but it still has to choose between
   * rotating and rendering as a guest once the access token ages out. This
   * carries that one bit and nothing else. Written by the API (and by SSR
   * rotation) — never re-stamped from the page, since a JS write is what invites
   * Safari's seven-day cap back in.
   */
  const sessionFlag = useCookie<string | null>('has_session', shared)

  /** True when a refresh token exists, as far as this environment can tell. */
  function hasSession() {
    if (import.meta.server) return Boolean(refreshToken.value || sessionFlag.value)
    return Boolean(sessionFlag.value)
  }

  function clearAuthCookies() {
    accessToken.value = null
    sessionFlag.value = null
    // Only meaningful during SSR; the browser's copy is HttpOnly and is retired
    // by the API's own Set-Cookie on logout.
    if (import.meta.server) refreshToken.value = null
  }

  return { accessToken, refreshToken, sessionFlag, hasSession, clearAuthCookies }
}

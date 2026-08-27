import { accessTokenNeedsRefresh } from '~/utils/jwtSession'

type ApiOptions = NonNullable<Parameters<typeof $fetch>[1]>

interface RefreshResponse {
  access?: string
  refresh?: string
}

interface SessionState {
  /** In-flight rotation, so concurrent callers share one refresh round-trip. */
  refreshFlight?: Promise<string | null> | null
  /**
   * Server-only: the access token rotated during this render. Nuxt's server
   * cookie refs read the *incoming* request header, so a token written mid-render
   * is invisible to every later `useCookie` call — without this, each SSR request
   * would keep presenting the superseded token and rotate again.
   */
  renderAccessToken?: string | null
}

const RECOVERABLE_REFRESH_STATUSES = [400, 401, 403]

/** The browser has exactly one session; SSR gets one state per request. */
const browserSession: SessionState = {}

function responseStatus(error: unknown) {
  if (!error || typeof error !== 'object') return 0
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } }
  return candidate.status || candidate.statusCode || candidate.response?.status || 0
}

/** `refresh_token_rotated` (retry) vs `token_not_valid` (session is over). */
function refreshFailureCode(error: unknown) {
  if (!error || typeof error !== 'object') return ''
  const candidate = error as { data?: { code?: unknown }; response?: { _data?: { code?: unknown } } }
  const code = candidate.data?.code ?? candidate.response?._data?.code
  return typeof code === 'string' ? code : ''
}

export const useApi = () => {
  const config = useRuntimeConfig()
  const { accessToken, refreshToken, sessionFlag, hasSession, clearAuthCookies } = useAuthCookies()
  const personalizationConsent = useCookie('revayato_personalization')
  // Resolved eagerly: useNuxtApp() needs the Nuxt context, which is not
  // guaranteed to still be attached after the first await below.
  const session: SessionState = import.meta.client
    ? browserSession
    : ((useNuxtApp() as unknown as { _revayatoSession?: SessionState })._revayatoSession ??= {})

  function currentAccessToken() {
    if (import.meta.server && session.renderAccessToken) return session.renderAccessToken
    return accessToken.value
  }

  function requestHeaders(options: ApiOptions, token = currentAccessToken()) {
    const headers = new Headers(options.headers as HeadersInit | undefined)
    headers.set('Accept', 'application/json')
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (import.meta.client && personalizationConsent.value === 'enabled') {
      const sessionId = sessionStorage.getItem('revayato:anonymous-session:v1')
      if (sessionId) headers.set('X-Anonymous-Session-ID', sessionId)
    }
    return headers
  }

  /**
   * Exchange the stored refresh token for a fresh access token.
   *
   * In the browser the request carries no token at all: the refresh cookie is
   * HttpOnly, so the browser attaches it and the API answers with a rotated
   * cookie the page never sees. A server render has no cookie jar of its own, so
   * it reads the incoming header and passes the token in the body instead, then
   * relays the rotated one onward through its own Set-Cookie.
   */
  async function rotateSession() {
    const result = await $fetch<RefreshResponse>('/auth/token/refresh/', {
      baseURL: import.meta.server ? config.apiInternalBase : config.public.apiBase,
      method: 'POST',
      headers: { Accept: 'application/json' },
      body: import.meta.server ? { refresh: refreshToken.value } : undefined,
      credentials: 'include',
      retry: 0,
    })
    if (!result?.access) return null
    accessToken.value = result.access
    if (import.meta.server) {
      session.renderAccessToken = result.access
      // Pass the rotated session on to the browser. Both writes become
      // Set-Cookie headers on this render's response.
      if (result.refresh) refreshToken.value = result.refresh
      sessionFlag.value = '1'
    }
    return result.access
  }

  async function refreshAccessToken() {
    if (!hasSession()) return null
    try {
      return await rotateSession()
    } catch (error) {
      const status = responseStatus(error)
      if (!RECOVERABLE_REFRESH_STATUSES.includes(status)) {
        // Network outages, rate limits and server errors do not invalidate an
        // otherwise valid persistent session. Let the caller retry later.
        throw error
      }
      // Rotation blacklists a refresh token the instant it is used, so two tabs
      // (or a retried request) can race and the loser is told its token is gone.
      // The winner's rotated cookie is already in the shared jar, and the browser
      // attaches it by itself — so a plain retry recovers a live session. A
      // render cannot benefit: the cookie it would need was written after this
      // request left the browser.
      if (import.meta.client && refreshFailureCode(error) === 'refresh_token_rotated') {
        try {
          const rotated = await rotateSession()
          if (rotated) return rotated
        } catch (retryError) {
          if (!RECOVERABLE_REFRESH_STATUSES.includes(responseStatus(retryError))) throw retryError
        }
      }
      if (import.meta.server) {
        // A render cannot prove the session is dead — it cannot see cookies the
        // browser received after this request left. Report the failure and let
        // the client, which reads the live jar, make that call.
        return null
      }
      // Refresh token truly invalid (expired, logged out elsewhere, or revoked).
      // The API has already retired its own cookies; drop what the page holds.
      clearAuthCookies()
      return null
    }
  }

  function sharedRefresh() {
    if (!session.refreshFlight) {
      session.refreshFlight = refreshAccessToken().finally(() => {
        session.refreshFlight = null
      })
    }
    return session.refreshFlight
  }

  /**
   * Rotate a fresh access token *before* it is needed, when one is missing or
   * about to expire. Without this, the first call after an idle hour either 401s
   * (an extra round-trip on every page) or — on the many endpoints that also
   * serve anonymous traffic — quietly returns public data, which is exactly what
   * "it logged me out" looks like even though the session never ended.
   */
  async function ensureFreshAccessToken() {
    const token = currentAccessToken()
    if (!hasSession()) return token
    if (!accessTokenNeedsRefresh(token)) return token
    try {
      return await sharedRefresh()
    } catch {
      // Transient failure: keep whatever token we have and let the request try.
      return currentAccessToken()
    }
  }

  async function execute<T>(request: string, options: ApiOptions, token = currentAccessToken()) {
    const requestToken = request.startsWith('/auth/') ? null : token
    return $fetch<T>(request, {
      ...options,
      // Server-side catalog rendering should use Docker's private network instead
      // of making a public round-trip through Caddy. The browser keeps using the
      // public same-origin endpoint.
      baseURL: import.meta.server ? config.apiInternalBase : config.public.apiBase,
      headers: requestHeaders(options, requestToken),
      retry: 0,
      // Catalog list endpoints can exceed 12s under crawler DB load; keep SSR
      // slightly higher so home does not paint an empty shell on every timeout.
      timeout: options.timeout ?? (import.meta.server ? 20_000 : 10_000),
    })
  }

  async function api<T>(request: string, options: ApiOptions = {}) {
    const authRequest = request.startsWith('/auth/')
    const token = authRequest ? null : await ensureFreshAccessToken()
    try {
      return await execute<T>(request, options, token)
    } catch (error) {
      if (responseStatus(error) !== 401 || authRequest || !hasSession()) throw error
      const refreshed = await sharedRefresh()
      if (!refreshed) throw error
      return execute<T>(request, options, refreshed)
    }
  }

  return { api, refreshAccessToken, ensureFreshAccessToken }
}

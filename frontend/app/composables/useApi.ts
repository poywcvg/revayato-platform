type ApiOptions = NonNullable<Parameters<typeof $fetch>[1]>

interface RefreshResponse {
  access: string
  refresh?: string
}

let clientRefreshRequest: Promise<string | null> | null = null

function responseStatus(error: unknown) {
  if (!error || typeof error !== 'object') return 0
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } }
  return candidate.status || candidate.statusCode || candidate.response?.status || 0
}

export const useApi = () => {
  const config = useRuntimeConfig()
  const { accessToken, refreshToken, clearAuthCookies } = useAuthCookies()
  const personalizationConsent = useCookie('revayato_personalization')

  function requestHeaders(options: ApiOptions, token = accessToken.value) {
    const headers = new Headers(options.headers as HeadersInit | undefined)
    headers.set('Accept', 'application/json')
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (import.meta.client && personalizationConsent.value === 'enabled') {
      const sessionId = sessionStorage.getItem('revayato:anonymous-session:v1')
      if (sessionId) headers.set('X-Anonymous-Session-ID', sessionId)
    }
    return headers
  }

  async function refreshAccessToken() {
    if (!refreshToken.value) return null
    try {
      const result = await $fetch<RefreshResponse>('/auth/token/refresh/', {
        baseURL: config.public.apiBase,
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: { refresh: refreshToken.value },
        retry: 0,
      })
      accessToken.value = result.access
      if (result.refresh) refreshToken.value = result.refresh
      return result.access
    } catch {
      clearAuthCookies()
      return null
    }
  }

  async function sharedRefresh() {
    if (!import.meta.client) return refreshAccessToken()
    if (!clientRefreshRequest) {
      clientRefreshRequest = refreshAccessToken().finally(() => {
        clientRefreshRequest = null
      })
    }
    return clientRefreshRequest
  }

  async function execute<T>(request: string, options: ApiOptions, token = accessToken.value) {
    const requestToken = request.startsWith('/auth/') ? null : token
    return $fetch<T>(request, {
      ...options,
      baseURL: config.public.apiBase,
      headers: requestHeaders(options, requestToken),
      retry: 0,
    })
  }

  async function api<T>(request: string, options: ApiOptions = {}) {
    try {
      return await execute<T>(request, options)
    } catch (error) {
      const authRequest = request.startsWith('/auth/')
      if (responseStatus(error) !== 401 || authRequest || !refreshToken.value) throw error
      const token = await sharedRefresh()
      if (!token) throw error
      return execute<T>(request, options, token)
    }
  }

  return { api, refreshAccessToken }
}

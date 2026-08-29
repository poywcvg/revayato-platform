import { defineStore } from 'pinia'
import type { AuthSession, Me } from '~/types'

function errorStatus(error: unknown) {
  if (!error || typeof error !== 'object') return 0
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } }
  return candidate.status || candidate.statusCode || candidate.response?.status || 0
}

export const useAuthStore = defineStore('auth', () => {
  const { accessToken, hasSession, clearAuthCookies } = useAuthCookies()
  const user = ref<Me | null>(null)
  const initialized = ref(false)
  const pending = ref(false)

  // The refresh token is HttpOnly, so "am I signed in?" is answered by the
  // credential-free session flag the API sets beside it — not by reading it.
  const isAuthenticated = computed(() => Boolean(accessToken.value || hasSession()))

  function endSession() {
    clearAuthCookies()
    user.value = null
    initialized.value = true
    if (import.meta.client) useNotifications().clear()
  }

  async function fetchMe() {
    if (!isAuthenticated.value) {
      user.value = null
      initialized.value = true
      return null
    }
    const { api } = useApi()
    try {
      user.value = await api<Me>('/accounts/me/')
      if (import.meta.client) {
        try {
          usePersonalizationState().ensureAccountPersonalization()
        } catch { /* optional during early boot */ }
      }
      return user.value
    } catch (error) {
      // Only a failed *refresh* can prove a session is over, and that path has
      // already cleared the cookies by the time we get here. A 401/403 while a
      // session is still on record means something else went wrong (a request
      // that raced rotation, a blip on one endpoint) — dropping the session then
      // is what logged people out for no reason.
      if ([401, 403].includes(errorStatus(error)) && !hasSession()) endSession()
      throw error
    } finally {
      initialized.value = true
    }
  }

  async function initialize() {
    if (initialized.value) return
    if (!isAuthenticated.value) {
      initialized.value = true
      return
    }
    try {
      await fetchMe()
    } catch {
      // A temporary network failure must not silently destroy a valid session.
    }
  }

  function applySession(session: AuthSession) {
    // `session.refresh` is deliberately ignored: the API delivered the browser's
    // copy as an HttpOnly cookie in this same response, which is what survives
    // Safari's seven-day cap on script-written cookies. The body still carries it
    // for the native app.
    accessToken.value = session.access
    user.value = session.user
    initialized.value = true
    if (import.meta.client) {
      try {
        usePersonalizationState().ensureAccountPersonalization()
      } catch { /* optional during early boot */ }
    }
  }

  async function login(login: string, password: string) {
    pending.value = true
    try {
      const { api } = useApi()
      const session = await api<AuthSession>('/auth/token/', {
        method: 'POST',
        body: { login: login.trim(), password },
      })
      applySession(session)
      return session.user
    } finally {
      pending.value = false
    }
  }

  async function register(email: string, username: string, password: string) {
    pending.value = true
    try {
      const { api } = useApi()
      const session = await api<AuthSession>('/auth/register/', {
        method: 'POST',
        body: { email: email.trim().toLowerCase(), username: username.trim(), password },
      })
      applySession(session)
      return session.user
    } finally {
      pending.value = false
    }
  }

  async function logout() {
    try {
      const { api } = useApi()
      // No body: the refresh token the API needs to blacklist is in the HttpOnly
      // cookie it issued, and this response is what retires it.
      await api('/auth/logout/', { method: 'POST', credentials: 'include' })
    } catch {
      // Local logout must always finish, even when the API is unavailable.
    } finally {
      endSession()
    }
  }

  async function updateProfile(payload: FormData | { bio?: string; preferred_language?: string; avatar?: null }) {
    pending.value = true
    try {
      const { api } = useApi()
      const updated = await api<Me>('/accounts/me/', {
        method: 'PATCH',
        body: payload,
      })
      user.value = updated
      return updated
    } finally {
      pending.value = false
    }
  }

  return {
    accessToken,
    user,
    initialized,
    pending,
    isAuthenticated,
    login,
    register,
    updateProfile,
    logout,
    fetchMe,
    initialize,
  }
})

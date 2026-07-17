import { defineStore } from 'pinia'
import type { AuthSession, Me } from '~/types'

function errorStatus(error: unknown) {
  if (!error || typeof error !== 'object') return 0
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } }
  return candidate.status || candidate.statusCode || candidate.response?.status || 0
}

export const useAuthStore = defineStore('auth', () => {
  const { accessToken, refreshToken, clearAuthCookies } = useAuthCookies()
  const user = ref<Me | null>(null)
  const initialized = ref(false)
  const pending = ref(false)

  const isAuthenticated = computed(() => Boolean(accessToken.value || refreshToken.value))

  async function fetchMe() {
    if (!isAuthenticated.value) {
      user.value = null
      initialized.value = true
      return null
    }
    const { api } = useApi()
    try {
      user.value = await api<Me>('/accounts/me/')
      return user.value
    } catch (error) {
      if (errorStatus(error) === 401 || errorStatus(error) === 403) {
        clearAuthCookies()
        user.value = null
        if (import.meta.client) useNotifications().clear()
      }
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
    accessToken.value = session.access
    refreshToken.value = session.refresh
    user.value = session.user
    initialized.value = true
  }

  async function login(email: string, password: string) {
    pending.value = true
    try {
      const { api } = useApi()
      const session = await api<AuthSession>('/auth/token/', {
        method: 'POST',
        body: { email: email.trim().toLowerCase(), password },
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
    const refresh = refreshToken.value
    try {
      if (refresh) {
        const { api } = useApi()
        await api('/auth/logout/', { method: 'POST', body: { refresh } })
      }
    } catch {
      // Local logout must always finish, even when the API is unavailable.
    } finally {
      clearAuthCookies()
      user.value = null
      initialized.value = true
      if (import.meta.client) useNotifications().clear()
    }
  }

  return {
    accessToken,
    refreshToken,
    user,
    initialized,
    pending,
    isAuthenticated,
    login,
    register,
    logout,
    fetchMe,
    initialize,
  }
})

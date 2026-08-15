// Chromium-based browsers cap persistent cookies at 400 days. Refresh-token
// rotation renews this window whenever an active user returns to the app.
export const AUTH_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 400

export function useAuthCookies() {
  const shared = {
    path: '/',
    sameSite: 'lax' as const,
    secure: import.meta.env.PROD,
  }
  const accessToken = useCookie<string | null>('access_token', {
    ...shared,
    maxAge: 60 * 60,
  })
  const refreshToken = useCookie<string | null>('refresh_token', {
    ...shared,
    maxAge: AUTH_SESSION_MAX_AGE_SECONDS,
  })

  function clearAuthCookies() {
    accessToken.value = null
    refreshToken.value = null
  }

  return { accessToken, refreshToken, clearAuthCookies }
}

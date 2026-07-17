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
    maxAge: 60 * 60 * 24 * 30,
  })

  function clearAuthCookies() {
    accessToken.value = null
    refreshToken.value = null
  }

  return { accessToken, refreshToken, clearAuthCookies }
}

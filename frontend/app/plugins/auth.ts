/**
 * Boots the session and then keeps it warm.
 *
 * A login is meant to survive until the user logs out. The 400-day window lives
 * in the API's HttpOnly cookie and is renewed every time that cookie rotates, so
 * the only thing the page has to do is rotate before the hourly access token
 * dies — otherwise the first request after an idle hour reaches a shared public
 * endpoint as an anonymous visitor, which is what "it logged me out" looks like.
 *
 * Rotation is triggered whenever the tab comes back into use: exactly the moment
 * a returning visitor would otherwise have met a stale session.
 */
const SESSION_HEARTBEAT_MS = 15 * 60 * 1000

export default defineNuxtPlugin(async () => {
  const authStore = useAuthStore()
  await authStore.initialize()

  if (!import.meta.client) return

  const { ensureFreshAccessToken } = useApi()

  async function keepSessionAlive() {
    if (!authStore.isAuthenticated) return
    try {
      await ensureFreshAccessToken()
    } catch {
      // Offline or a server blip: the session stays, the next tick tries again.
    }
  }

  const onVisibility = () => {
    if (document.visibilityState === 'visible') keepSessionAlive()
  }

  window.setInterval(keepSessionAlive, SESSION_HEARTBEAT_MS)
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('focus', keepSessionAlive)
  window.addEventListener('online', keepSessionAlive)
})

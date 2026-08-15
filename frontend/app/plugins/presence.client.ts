/**
 * Client heartbeat for accurate online analytics.
 * Pings Redis-backed /api/analytics/presence/ while the tab is visible.
 */
const SESSION_KEY = 'revayato:anonymous-session:v1'
const INTERVAL_MS = 45_000

function ensureSessionId() {
  try {
    let id = sessionStorage.getItem(SESSION_KEY)
    if (!id) {
      id = (globalThis.crypto?.randomUUID?.() || `anon-${Date.now().toString(36)}`).slice(0, 80)
      sessionStorage.setItem(SESSION_KEY, id)
    }
    return id
  } catch {
    return `anon-${Date.now().toString(36)}`
  }
}

export default defineNuxtPlugin(() => {
  const { api } = useApi()
  let timer: ReturnType<typeof setInterval> | null = null
  let inFlight = false

  async function ping() {
    if (!import.meta.client || document.hidden || inFlight) return
    inFlight = true
    try {
      await api('/analytics/presence/', {
        method: 'POST',
        body: {
          anonymous_session_id: ensureSessionId(),
          path: (window.location.pathname || '/').slice(0, 180),
        },
      })
    } catch {
      // Presence is best-effort; never block UX.
    } finally {
      inFlight = false
    }
  }

  function start() {
    if (timer) return
    void ping()
    timer = setInterval(() => { void ping() }, INTERVAL_MS)
  }

  function stop() {
    if (!timer) return
    clearInterval(timer)
    timer = null
  }

  const onVisibility = () => {
    if (document.hidden) stop()
    else start()
  }

  if (document.readyState === 'complete') start()
  else window.addEventListener('load', start, { once: true })
  document.addEventListener('visibilitychange', onVisibility)

  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    })
  }
})

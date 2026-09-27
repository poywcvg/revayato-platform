import { describeMediaUrl, reportClientDiag } from '~/utils/clientDiag'

/**
 * Reports uncaught errors, and on player pages a snapshot of the <video>
 * element a few seconds in — the two things a "black player" report needs and
 * the server can never see on its own.
 */
export default defineNuxtPlugin((nuxtApp) => {
  const isPlayerPage = () => /^\/watch(-party)?\//.test(window.location.pathname)

  nuxtApp.hook('vue:error', (error, _instance, info) => {
    reportClientDiag('vue-error', { info: String(info || '') }, error)
  })
  nuxtApp.hook('app:error', (error) => {
    reportClientDiag('app-error', {}, error)
  })
  window.addEventListener('error', (event) => {
    if (!isPlayerPage()) return
    reportClientDiag('window-error', { source: `${event.filename || ''}:${event.lineno || 0}:${event.colno || 0}` }, event.error || event.message)
  })
  window.addEventListener('unhandledrejection', (event) => {
    if (!isPlayerPage()) return
    reportClientDiag('unhandled-rejection', {}, event.reason)
  })

  const snapshotPlayer = (label: string) => {
    if (!isPlayerPage()) return
    const player = document.querySelector<HTMLElement>('[data-video-player]')
    const video = player?.querySelector('video') || null
    const buffered = video?.buffered
    reportClientDiag('player-snapshot', {
      label,
      playerMounted: Boolean(player),
      busy: player?.getAttribute('aria-busy') || '',
      overlay: (player?.querySelector('[role="alert"], [role="status"]')?.textContent || '').trim().slice(0, 200),
      video: video
        ? {
            src: describeMediaUrl(video.currentSrc || video.src),
            readyState: video.readyState,
            networkState: video.networkState,
            error: video.error ? { code: video.error.code, message: video.error.message } : null,
            paused: video.paused,
            currentTime: Math.round(video.currentTime),
            duration: Number.isFinite(video.duration) ? Math.round(video.duration) : String(video.duration),
            videoWidth: video.videoWidth,
            videoHeight: video.videoHeight,
            bufferedEnd: buffered && buffered.length ? Math.round(buffered.end(buffered.length - 1)) : 0,
          }
        : null,
    })
  }

  let timers: number[] = []
  const armSnapshots = () => {
    timers.forEach(timer => window.clearTimeout(timer))
    timers = []
    if (!isPlayerPage()) return
    timers.push(window.setTimeout(() => snapshotPlayer('8s'), 8_000))
    timers.push(window.setTimeout(() => snapshotPlayer('25s'), 25_000))
  }
  nuxtApp.hook('app:mounted', armSnapshots)
  nuxtApp.hook('page:finish', armSnapshots)
})

/**
 * Tiny beacon for errors and player state that only a real browser sees.
 * Lands in the frontend container log via server/routes/client-diag.post.ts.
 * Sends no user data: the page path, the browser's UA, and what went wrong.
 */
const MAX_REPORTS_PER_PAGE = 12
let sent = 0

function describeError(error: unknown) {
  if (error instanceof Error) {
    return { name: error.name, message: error.message, stack: String(error.stack || '').split('\n').slice(0, 12).join('\n') }
  }
  try {
    return { message: typeof error === 'string' ? error : JSON.stringify(error) }
  }
  catch {
    return { message: String(error) }
  }
}

/** Media URL reduced to host + extension: enough to tell sources apart. */
export function describeMediaUrl(url?: string | null) {
  const raw = String(url || '').trim()
  if (!raw) return ''
  if (raw.startsWith('blob:')) return 'blob'
  try {
    const parsed = new URL(raw, window.location.href)
    const ext = (parsed.pathname.match(/\.([a-z0-9]{2,5})$/i)?.[1] || '').toLowerCase()
    return `${parsed.host}${ext ? ` .${ext}` : ''}`
  }
  catch {
    return 'unparsable'
  }
}

export function reportClientDiag(kind: string, detail: Record<string, unknown> = {}, error?: unknown) {
  if (!import.meta.client || sent >= MAX_REPORTS_PER_PAGE) return
  sent += 1
  try {
    const body = JSON.stringify({
      kind,
      path: window.location.pathname,
      ua: navigator.userAgent,
      at: Math.round(performance.now()),
      ...detail,
      ...(error === undefined ? {} : { error: describeError(error) }),
    })
    const blob = new Blob([body], { type: 'application/json' })
    if (!navigator.sendBeacon?.('/client-diag', blob)) {
      void fetch('/client-diag', { method: 'POST', body, headers: { 'content-type': 'application/json' }, keepalive: true }).catch(() => {})
    }
  }
  catch {
    /* diagnostics must never break the page */
  }
}

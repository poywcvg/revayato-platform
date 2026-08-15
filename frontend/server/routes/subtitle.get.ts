/**
 * Same-origin SoftSub proxy.
 * Browser fetch of CDN VTT often fails CORS; the player loads `/subtitle?url=…` instead.
 */
export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const raw = String(query.url || '').trim()
  if (!raw) {
    throw createError({ statusCode: 400, statusMessage: 'Missing subtitle url' })
  }

  let target: URL
  try {
    target = new URL(raw)
  } catch {
    throw createError({ statusCode: 400, statusMessage: 'Invalid subtitle url' })
  }

  if (target.protocol !== 'http:' && target.protocol !== 'https:') {
    throw createError({ statusCode: 400, statusMessage: 'Unsupported subtitle protocol' })
  }

  // Only proxy likely subtitle assets.
  const path = target.pathname.toLowerCase()
  const looksLikeSubtitle = (
    path.includes('/media/')
    || path.includes('subtitle')
    || path.includes('softsub')
    || /\.(vtt|webvtt|srt|ass|ssa)($|\.)/i.test(path)
  )
  if (!looksLikeSubtitle) {
    throw createError({ statusCode: 400, statusMessage: 'URL is not a subtitle asset' })
  }

  let upstream: Response
  try {
    upstream = await fetch(target.toString(), {
      headers: {
        Accept: 'text/vtt,text/plain,application/octet-stream,*/*',
        'User-Agent': 'RevayatoSubtitleProxy/1.0',
      },
      redirect: 'follow',
    })
  } catch {
    throw createError({ statusCode: 502, statusMessage: 'Subtitle upstream unreachable' })
  }

  if (!upstream.ok) {
    throw createError({
      statusCode: upstream.status === 404 ? 404 : 502,
      statusMessage: `Subtitle upstream ${upstream.status}`,
    })
  }

  const text = await upstream.text()
  if (!text.trim()) {
    throw createError({ statusCode: 502, statusMessage: 'Empty subtitle payload' })
  }

  const contentType = upstream.headers.get('content-type') || 'text/vtt; charset=utf-8'
  setHeader(event, 'content-type', contentType.includes('text') ? contentType : 'text/vtt; charset=utf-8')
  setHeader(event, 'cache-control', 'public, max-age=3600, stale-while-revalidate=86400')
  setHeader(event, 'access-control-allow-origin', '*')
  return text
})

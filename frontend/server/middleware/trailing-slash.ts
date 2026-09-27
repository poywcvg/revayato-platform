/**
 * `/movies/inception-2010/` and `/movies/inception-2010` rendered the same page
 * with a 200 each — two URLs competing for one ranking. Send every page address
 * with a trailing slash to the slash-less one (the canonical) permanently.
 */
const SKIP_PREFIXES = ['/api/', '/_nuxt/', '/_ipx/', '/__nuxt', '/media/', '/static/', '/downloads/', '/ws/']

export default defineEventHandler((event) => {
  if (event.method !== 'GET' && event.method !== 'HEAD') return
  const url = event.path || '/'
  const queryAt = url.indexOf('?')
  const path = queryAt === -1 ? url : url.slice(0, queryAt)
  if (path.length <= 1 || !path.endsWith('/')) return
  if (SKIP_PREFIXES.some(prefix => path.startsWith(prefix))) return
  // Collapse leading slashes too: `//evil.example/` must never become a
  // protocol-relative redirect to another host.
  const target = `/${path.replace(/^\/+/, '').replace(/\/+$/, '')}` + (queryAt === -1 ? '' : url.slice(queryAt))
  return sendRedirect(event, target, 301)
})

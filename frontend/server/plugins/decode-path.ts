/**
 * Nuxt's renderer runs `encodePath(event.path)`. On a normal request h3 has
 * already decoded the path, but routes cached through `routeRules` (swr) are
 * rendered on a fresh event built from `req.url`, which h3 restores to the raw,
 * already percent-encoded URL on every layer. Every non-ASCII page address
 * (actor names, Persian genre slugs, usernames…) then rendered with
 * `%25`-double-encoded canonical / og:url and a `_payload.json` URL that 404s.
 *
 * A middleware is too late (h3 captures the raw URL before any runs), so hand
 * page requests to the app already decoded; the renderer encodes them once.
 * `decodeURI` leaves reserved escapes (%2F, %3F, %23…) alone.
 */
const SKIP_PREFIXES = ['/api/', '/_nuxt/', '/_ipx/', '/media/', '/static/', '/downloads/', '/ws/']

function decodePagePath(url: string): string {
  const queryAt = url.indexOf('?')
  const path = queryAt === -1 ? url : url.slice(0, queryAt)
  if (!path.includes('%') || SKIP_PREFIXES.some(prefix => path.startsWith(prefix))) return url
  try {
    const decoded = decodeURI(path)
    return decoded === path ? url : decoded + (queryAt === -1 ? '' : url.slice(queryAt))
  }
  catch {
    return url
  }
}

export default defineNitroPlugin((nitroApp) => {
  const handler = nitroApp.h3App.handler
  nitroApp.h3App.handler = ((event) => {
    const req = event.node.req
    if (req.url) req.url = decodePagePath(req.url)
    return handler(event)
  }) as typeof handler
})

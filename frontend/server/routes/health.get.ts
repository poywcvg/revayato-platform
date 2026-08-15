/**
 * Lightweight liveness probe for Docker/Caddy — avoids SSR + catalog fan-out.
 */
export default defineEventHandler((event) => {
  setHeader(event, 'cache-control', 'no-store')
  setHeader(event, 'content-type', 'application/json; charset=utf-8')
  return { status: 'ok', service: 'revayato-frontend' }
})

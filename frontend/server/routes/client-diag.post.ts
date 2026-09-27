/**
 * Receives player/page diagnostics from browsers (utils/clientDiag) and writes
 * them to the frontend container log as one `[client-diag]` JSON line each.
 * No IP, cookie or user id is read or logged — only what the page sent, capped.
 */
const MAX_FIELD = 1500

function clip(value: unknown): unknown {
  if (typeof value === 'string') return value.slice(0, MAX_FIELD)
  if (typeof value === 'number' || typeof value === 'boolean' || value == null) return value
  if (Array.isArray(value)) return value.slice(0, 20).map(clip)
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [key, inner] of Object.entries(value as Record<string, unknown>).slice(0, 40)) out[key.slice(0, 40)] = clip(inner)
    return out
  }
  return String(value).slice(0, MAX_FIELD)
}

export default defineEventHandler(async (event) => {
  try {
    const raw = await readRawBody(event, 'utf8')
    if (raw && raw.length <= 16_000) {
      console.log(`[client-diag] ${JSON.stringify(clip(JSON.parse(raw)))}`)
    }
  }
  catch {
    /* malformed beacon: drop it */
  }
  setResponseStatus(event, 204)
  return null
})

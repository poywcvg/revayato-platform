/**
 * The IndexNow key file. Bing/Yandex fetch it to confirm that the URLs the
 * backend submits belong to this host (see backend apps/catalog/indexnow.py,
 * the key's only source).
 */
export default defineEventHandler(async (event) => {
  const { apiBase } = sitemapContext(event)
  let key = ''
  try {
    key = String(await $fetch<string>(`${apiBase}/catalog/indexnow-key/`, { responseType: 'text', timeout: 5000, retry: 1 })).trim()
  } catch {
    key = ''
  }
  if (!key) throw createError({ statusCode: 404, statusMessage: 'Not Found' })
  setHeader(event, 'Content-Type', 'text/plain; charset=utf-8')
  setHeader(event, 'Cache-Control', 'public, max-age=86400')
  return key
})

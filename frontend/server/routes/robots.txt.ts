export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event)
  const siteUrl = String(config.public.siteUrl).replace(/\/$/, '')

  setHeader(event, 'content-type', 'text/plain; charset=utf-8')
  setHeader(event, 'cache-control', 'public, max-age=3600')

  // SEO-tool crawlers bring no visitors but walk every actor/title page cold on
  // a small, shared CPU — they were a large share of the site's SSR load.
  const blocked = ['AhrefsBot', 'SemrushBot', 'MJ12bot', 'DotBot', 'BLEXBot', 'PetalBot', 'DataForSeoBot', 'Bytespider', 'serpstatbot']

  return [
    ...blocked.flatMap(agent => [`User-agent: ${agent}`, 'Disallow: /', '']),
    // Honoured by Bing/Yandex (Google ignores it and self-throttles).
    'User-agent: bingbot',
    'User-agent: YandexBot',
    'Crawl-delay: 2',
    'Allow: /',
    'Disallow: /api/',
    'Disallow: /admin/',
    'Disallow: /auth/',
    'Disallow: /profile/',
    'Disallow: /watch-party/',
    '',
    'User-agent: *',
    'Allow: /',
    'Disallow: /api/',
    'Disallow: /admin/',
    'Disallow: /admin',
    'Disallow: /auth/',
    'Disallow: /profile/',
    'Disallow: /watch-party/',
    `Sitemap: ${siteUrl}/sitemap.xml`,
    '',
  ].join('\n')
})

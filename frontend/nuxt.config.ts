import tailwindcss from '@tailwindcss/vite'

const trimBase = (value?: string) => String(value || '').replace(/\/$/, '')
const configuredApiBase = trimBase(process.env.NUXT_PUBLIC_API_BASE)
  || (process.env.API_BASE_URL ? `${trimBase(process.env.API_BASE_URL)}/api` : '/api')

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',

  modules: [
    '@pinia/nuxt',
    '@vueuse/nuxt',
    '@nuxt/eslint',
    '@nuxt/fonts',
    '@nuxt/image',
    ['unplugin-icons/nuxt', {
      compiler: 'vue3',
      autoInstall: false,
      scale: 1,
      defaultClass: 'lucide-icon',
    }],
  ],

  css: ['vue-sonner/style.css', '~/assets/css/main.css'],

  components: [{ path: '~/components', pathPrefix: false }],

  imports: { dirs: ['composables/**'] },

  vite: { plugins: [tailwindcss()] },

  runtimeConfig: {
    apiInternalBase: process.env.NUXT_API_INTERNAL_BASE || '/api',
    public: {
      apiBase: configuredApiBase,
      wsBase: trimBase(process.env.NUXT_PUBLIC_WS_BASE),
      siteUrl: trimBase(process.env.NUXT_PUBLIC_SITE_URL || process.env.SITE_BASE_URL),
      mediaCdnBaseUrl: trimBase(process.env.NUXT_PUBLIC_MEDIA_CDN_BASE_URL || process.env.MEDIA_CDN_BASE_URL),
      downloadCdnBaseUrl: trimBase(process.env.NUXT_PUBLIC_DOWNLOAD_CDN_BASE_URL || process.env.DOWNLOAD_CDN_BASE_URL),
      catalogSource: process.env.NUXT_PUBLIC_CATALOG_SOURCE || 'api',
      analyticsTransport: process.env.NUXT_PUBLIC_ANALYTICS_TRANSPORT || 'local',
      eventsEndpoint: process.env.NUXT_PUBLIC_EVENTS_ENDPOINT || '/events/',
    },
  },

  fonts: {
    // Self-host via npm so Latin/Persian fonts work in Iran without Google CDN.
    provider: 'npm',
    defaults: {
      weights: [400, 700],
      styles: ['normal'],
      formats: ['woff2'],
      preload: false,
      fallbacks: {
        'sans-serif': ['Tahoma', 'Arial', 'sans-serif'],
      },
    },
    families: [
      {
        name: 'Vazirmatn',
        provider: 'npm',
        weights: [400, 700],
        styles: ['normal'],
        global: true,
        // Preload body weight only — bold swaps in after first paint.
        preload: true,
        display: 'swap',
      },
      {
        // English / Latin UI — sits ahead of Vazirmatn for Latin glyphs site-wide.
        name: 'Plus Jakarta Sans',
        provider: 'npm',
        weights: [500, 700],
        styles: ['normal'],
        global: true,
        preload: false,
        display: 'swap',
      },
    ],
  },

  image: {
    format: ['webp'],
    quality: 72,
    densities: [1],
    screens: { xs: 375, sm: 640, md: 768, lg: 1024, xl: 1280, xxl: 1536 },
    domains: [
      'image.tmdb.org',
      'revayato.com',
      'www.revayato.com',
      ...(process.env.NUXT_IMAGE_DOMAINS || '')
        .split(',')
        .map(d => d.trim())
        .filter(Boolean),
    ],
    presets: {
      cinemaPoster: { modifiers: { width: 360, height: 540, format: 'webp', quality: 70 } },
      cinemaBackdrop: { modifiers: { width: 1280, height: 720, format: 'webp', quality: 70 } },
      cinemaTile: { modifiers: { width: 720, height: 480, format: 'webp', quality: 68 } },
    },
  },

  app: {
    // Brief out-in fade: leave finishes before enter so layout never stacks.
    pageTransition: {
      name: 'cinema-page',
      mode: 'out-in',
      appear: false,
    },
    layoutTransition: {
      name: 'cinema-layout',
      mode: 'out-in',
    },
    head: {
      htmlAttrs: { lang: 'fa', dir: 'rtl' },
      bodyAttrs: { class: 'rtl' },
      title: 'روایتو',
      titleTemplate: '%s | روایتو',
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/favicon-32.png' },
        { rel: 'apple-touch-icon', sizes: '180x180', href: '/apple-touch-icon.png' },
        { rel: 'manifest', href: '/site.webmanifest' },
      ],
      meta: [
        { name: 'application-name', content: 'روایتو' },
        { name: 'description', content: 'در روایتو فیلم و سریال را پیدا کن، تماشا کن و تجربه‌ات را با دوستانت به اشتراک بگذار.' },
        { property: 'og:site_name', content: 'روایتو' },
        { property: 'og:locale', content: 'fa_IR' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'theme-color', content: '#1d1c21' },
      ],
      script: [
        {
          // Dark-only theme + kill browser scroll restore before first paint.
          innerHTML: `(function(){try{localStorage.setItem('revayato-theme','dark');document.documentElement.dataset.theme='dark';document.documentElement.style.colorScheme='dark';var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute('content','#1d1c21');if('scrollRestoration'in history)history.scrollRestoration='manual';if(!location.hash){var r=document.documentElement;r.scrollTop=0;if(document.body)document.body.scrollTop=0;window.scrollTo(0,0)}}catch(e){document.documentElement.dataset.theme='dark';document.documentElement.style.colorScheme='dark'}})()`,
          tagPosition: 'head',
        },
      ],
    },
  },

  experimental: { payloadExtraction: true, renderJsonPayloads: true },
  devtools: { enabled: false },
  nitro: { compressPublicAssets: true },
  routeRules: {
    '/': { swr: 120 },
    '/movies': { swr: 180 },
    '/series': { swr: 180 },
    '/new': { swr: 120 },
    '/_nuxt/**': { headers: { 'cache-control': 'public, max-age=31536000, immutable' } },
    '/_ipx/**': { headers: { 'cache-control': 'public, max-age=2592000, stale-while-revalidate=86400' } },
    '/media/**': { headers: { 'cache-control': 'public, max-age=2592000, stale-while-revalidate=86400' } },
    // Staff panel is auth-gated; skip SSR to free Nuxt workers for public pages.
    '/admin/**': { ssr: false },
  },
})

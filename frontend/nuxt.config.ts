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
      catalogSource: process.env.NUXT_PUBLIC_CATALOG_SOURCE || 'mock',
      analyticsTransport: process.env.NUXT_PUBLIC_ANALYTICS_TRANSPORT || 'local',
      eventsEndpoint: process.env.NUXT_PUBLIC_EVENTS_ENDPOINT || '/events/',
    },
  },

  fonts: {
    provider: 'google',
    defaults: {
      weights: [400, 500, 600, 700],
      styles: ['normal'],
      formats: ['woff2'],
      preload: true,
    },
    families: [
      {
        name: 'Vazirmatn',
        provider: 'google',
        weights: [400, 500, 600, 700],
        styles: ['normal'],
        subsets: ['arabic', 'latin'],
        global: true,
        preload: true,
      },
      {
        name: 'Inter',
        provider: 'google',
        weights: [400, 500, 600, 700],
        styles: ['normal'],
        subsets: ['latin'],
        global: true,
        preload: false,
      },
    ],
  },

  image: {
    format: ['webp'],
    quality: 80,
    densities: [1, 2],
    screens: { xs: 375, sm: 640, md: 768, lg: 1024, xl: 1280, xxl: 1536 },
    presets: {
      cinemaPoster: { modifiers: { width: 360, height: 540 } },
      cinemaBackdrop: { modifiers: { width: 1280, height: 720 } },
      cinemaTile: { modifiers: { width: 720, height: 480 } },
    },
  },

  app: {
    head: {
      htmlAttrs: { lang: 'fa', dir: 'rtl' },
      title: 'روایتو',
      titleTemplate: '%s | روایتو',
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'manifest', href: '/site.webmanifest' },
      ],
      meta: [
        { name: 'application-name', content: 'روایتو' },
        { name: 'description', content: 'در روایتو فیلم و سریال را پیدا کن، تماشا کن و تجربه‌ات را با دوستانت به اشتراک بگذار.' },
        { property: 'og:site_name', content: 'روایتو' },
        { property: 'og:locale', content: 'fa_IR' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'theme-color', content: '#060607' },
      ],
    },
  },

  experimental: { payloadExtraction: true, renderJsonPayloads: true },
  devtools: { enabled: false },
  nitro: { compressPublicAssets: true },
  routeRules: {
    '/_nuxt/**': { headers: { 'cache-control': 'public, max-age=31536000, immutable' } },
    '/_ipx/**': { headers: { 'cache-control': 'public, max-age=2592000, stale-while-revalidate=86400' } },
    '/media/**': { headers: { 'cache-control': 'public, max-age=2592000, stale-while-revalidate=86400' } },
  },
})

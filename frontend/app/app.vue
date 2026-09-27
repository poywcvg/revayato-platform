<template>
  <NuxtLoadingIndicator
    color="linear-gradient(90deg, #408a71, #c8efdc 52%, #b0e4cc)"
    :height="2"
    :duration="220"
    :throttle="0"
  />
  <RouteLoader />
  <NuxtRouteAnnouncer />
  <AppNotifications />
  <SupportModal />
  <AppInstallNudge />
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>

<script setup lang="ts">
const config = useRuntimeConfig()
const route = useRoute()
const siteUrl = computed(() => String(config.public.siteUrl).replace(/\/$/, ''))

useTheme()

// One address per page: no trailing slash, no query (filters/sort/tracking are
// views of the same page). Pages whose query IS the content (landing ?page=N)
// emit their own canonical, which replaces this one (same dedupe key).
const canonicalPath = computed(() => (route.path.length > 1 ? route.path.replace(/\/+$/, '') : route.path) || '/')

useHead({
  link: [
    { rel: 'canonical', href: () => `${siteUrl.value}${canonicalPath.value}` },
  ],
  meta: [
    { property: 'og:url', content: () => `${siteUrl.value}${canonicalPath.value}` },
    { property: 'og:type', content: 'website' },
  ],
  // Belt-and-suspenders: if JS is disabled entirely, the scroll-reveal attribute
  // gate never applies, but this guarantees no .reveal node can stay hidden.
  noscript: [
    {
      innerHTML: '<style>.reveal{opacity:1!important;transform:none!important}</style>',
    },
  ],
})

// Sitelinks search box + brand identity — only meaningful on the home page.
useHead(() => (route.path === '/' ? {
  script: [{
    key: 'site-jsonld',
    type: 'application/ld+json',
    innerHTML: jsonLdString({
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'WebSite',
          '@id': `${siteUrl.value}/#website`,
          url: `${siteUrl.value}/`,
          name: SITE_NAME,
          alternateName: ['Revayato', 'روایتو'],
          inLanguage: 'fa-IR',
          publisher: { '@id': `${siteUrl.value}/#organization` },
          potentialAction: {
            '@type': 'SearchAction',
            target: { '@type': 'EntryPoint', urlTemplate: `${siteUrl.value}/search?q={search_term_string}` },
            'query-input': 'required name=search_term_string',
          },
        },
        {
          '@type': 'Organization',
          '@id': `${siteUrl.value}/#organization`,
          name: SITE_NAME,
          alternateName: 'Revayato',
          url: `${siteUrl.value}/`,
          logo: { '@type': 'ImageObject', url: `${siteUrl.value}/icon-512.png?v=2`, width: 512, height: 512 },
        },
      ],
    }),
  }],
} : {}))
</script>

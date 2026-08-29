<template>
  <NuxtLoadingIndicator
    color="linear-gradient(90deg, #285a48, #b0e4cc 55%, #408a71)"
    :height="3"
    :duration="600"
    :throttle="40"
  />
  <NuxtRouteAnnouncer />
  <AppNotifications />
  <SupportModal />
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>

<script setup lang="ts">
const config = useRuntimeConfig()
const route = useRoute()
const siteUrl = computed(() => String(config.public.siteUrl).replace(/\/$/, ''))

useTheme()

useHead({
  link: [
    { rel: 'canonical', href: () => `${siteUrl.value}${route.path}` },
  ],
  meta: [
    { property: 'og:url', content: () => `${siteUrl.value}${route.path}` },
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
</script>

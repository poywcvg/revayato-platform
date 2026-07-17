<template>
  <NuxtLoadingIndicator color="#C46A2D" :height="2" :throttle="80" />
  <NuxtRouteAnnouncer />
  <AppNotifications />
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>

<script setup lang="ts">
const config = useRuntimeConfig()
const route = useRoute()
const siteUrl = computed(() => String(config.public.siteUrl).replace(/\/$/, ''))

useHead({
  link: [
    { rel: 'canonical', href: () => `${siteUrl.value}${route.path}` },
  ],
  meta: [
    { property: 'og:url', content: () => `${siteUrl.value}${route.path}` },
    { property: 'og:type', content: 'website' },
  ],
})
</script>

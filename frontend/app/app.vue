<template>
  <NuxtLoadingIndicator
    color="linear-gradient(90deg, #285a48, #b0e4cc 55%, #408a71)"
    :height="3"
    :duration="1500"
    :throttle="60"
  />
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

useTheme()

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

<script setup lang="ts">
const route = useRoute()
const config = useRuntimeConfig()
const { movie: series, refresh } = useMovieBySlug(() => String(route.params.slug), 'series')
if (config.public.catalogSource === 'api' || !series.value?.episodes?.length) await refresh()
if (!series.value || series.value.type !== 'series') throw createError({ statusCode: 404, statusMessage: 'سریال پیدا نشد' })
useSeoMeta({ title: () => series.value?.title || 'سریال', description: () => series.value?.description || '', ogTitle: () => series.value?.title, ogDescription: () => series.value?.description, ogImage: () => series.value?.backdrop_url, twitterCard: 'summary_large_image' })
</script>

<template>
  <CatalogDetail v-if="series" :item="series" />
</template>

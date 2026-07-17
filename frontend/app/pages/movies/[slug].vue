<script setup lang="ts">
const route = useRoute()
const config = useRuntimeConfig()
const { movie, refresh } = useMovieBySlug(() => String(route.params.slug), 'movie')
if (config.public.catalogSource === 'api') await refresh()
if (!movie.value || movie.value.type !== 'movie') throw createError({ statusCode: 404, statusMessage: 'فیلم پیدا نشد' })
useSeoMeta({ title: () => movie.value?.title || 'فیلم', description: () => movie.value?.description || '', ogTitle: () => movie.value?.title, ogDescription: () => movie.value?.description, ogImage: () => movie.value?.backdrop_url, twitterCard: 'summary_large_image' })
</script>

<template>
  <CatalogDetail v-if="movie" :item="movie" />
</template>

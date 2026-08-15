<script setup lang="ts">
/**
 * Legacy home "تازه‌ها" linked to /search?sort=newest.
 * Send bare newest-browse traffic to /new; keep real search/filter queries here.
 */
const route = useRoute()

const filterKeys = [
  'q',
  'genre',
  'year',
  'age',
  'country',
  'language',
  'availability',
  'format',
  'min_rating',
] as const

const hasSearchOrFilter = filterKeys.some((key) => {
  const value = route.query[key]
  const raw = Array.isArray(value) ? value[0] : value
  return Boolean(raw && String(raw).trim() && String(raw) !== 'all')
})

if (!hasSearchOrFilter && String(route.query.sort || '') === 'newest') {
  const type = route.query.type === 'movie' || route.query.type === 'series'
    ? route.query.type
    : undefined
  await navigateTo(
    { path: '/new', query: type ? { type } : {} },
    { redirectCode: 301, replace: true },
  )
}

useSeoMeta({
  title: 'جستجوی پیشرفته',
  description: 'فیلم و سریال را با نام، ژانر، سال، امتیاز و فیلترهای دقیق پیدا کن.',
})
</script>

<template>
  <CatalogBrowser discovery />
</template>

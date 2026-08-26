<script setup lang="ts">
const route = useRoute()
const slug = computed(() => String(route.params.slug))
const { movie: series, refresh, pending } = useMovieBySlug(slug, 'series')

// Always load detail so episodes / cast / download URLs are present.
await refresh()

if (!series.value || series.value.type !== 'series') {
  throw createError({ statusCode: 404, message: 'سریال پیدا نشد' })
}

const castNames = computed(() => (series.value?.cast || []).slice(0, 8).map(person => person.name).filter(Boolean))
const downloadQualities = computed(() => series.value?.download_qualities || [])
const seoTitle = computed(() => series.value?.seo_title || series.value?.title || 'سریال')
const seoDescription = computed(() => {
  if (series.value?.seo_description) return series.value.seo_description
  const base = (series.value?.description || '').slice(0, 160)
  const bits = []
  if (castNames.value.length) bits.push(`بازیگران: ${castNames.value.join('، ')}`)
  if (downloadQualities.value.length) bits.push(`دانلود: ${downloadQualities.value.join('، ')}`)
  return `${base}${bits.length ? ` ${bits.join(' ')}` : ''}`.slice(0, 320)
})
const seoKeywords = computed(() => {
  const fromApi = series.value?.seo_keywords || []
  const local = [
    series.value?.title,
    series.value?.original_title,
    series.value?.has_downloads ? 'دانلود' : '',
    ...downloadQualities.value,
    ...castNames.value,
    ...(series.value?.genres || []).map(genre => genre.title),
  ].filter(Boolean) as string[]
  return [...new Set([...fromApi, ...local])].join(', ')
})

useSeoMeta({
  title: seoTitle,
  description: seoDescription,
  ogTitle: seoTitle,
  ogDescription: seoDescription,
  ogImage: () => series.value?.backdrop_url,
  twitterCard: 'summary_large_image',
  keywords: seoKeywords,
})

useHead(() => {
  const item = series.value
  if (!item) return {}
  const site = (item.ratings || []).find(entry => entry.source === 'site' && entry.value > 0)
  return {
    script: [{
      type: 'application/ld+json',
      children: JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'TVSeries',
        name: item.title,
        alternateName: item.original_title,
        description: seoDescription.value,
        image: item.poster_url,
        dateCreated: item.year ? String(item.year) : undefined,
        genre: item.genres.map(genre => genre.title),
        actor: item.cast.slice(0, 10).map(person => ({ '@type': 'Person', name: person.name })),
        // Only website user ratings — never IMDb/TMDB as aggregateRating.
        aggregateRating: site ? {
          '@type': 'AggregateRating',
          ratingValue: site.value,
          bestRating: site.scale,
          ...(site.voteCount ? { ratingCount: site.voteCount } : {}),
        } : undefined,
        keywords: seoKeywords.value,
      }),
    }],
  }
})
</script>

<template>
  <!-- Single root required for Nuxt pageTransition (out-in); multi-root blanks the page. -->
  <div>
    <CatalogDetail v-if="series" :item="series" />
    <div v-else-if="pending" class="media-detail content-section grid min-h-[55svh] place-items-center py-10" aria-busy="true">
      <LoadingSpinnerA size="large">در حال آماده‌سازی صفحه سریال…</LoadingSpinnerA>
    </div>
  </div>
</template>

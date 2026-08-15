<script setup lang="ts">
const route = useRoute()
const slug = computed(() => String(route.params.slug))
const { movie, refresh, pending } = useMovieBySlug(slug, 'movie')

// Always load detail so download_links / cast are present (list cache omits them).
await refresh()

if (!movie.value || movie.value.type !== 'movie') {
  throw createError({ statusCode: 404, message: 'فیلم پیدا نشد' })
}

const castNames = computed(() => (movie.value?.cast || []).slice(0, 8).map(person => person.name).filter(Boolean))
const downloadQualities = computed(() => movie.value?.download_qualities || [])
const seoTitle = computed(() => movie.value?.seo_title || movie.value?.title || 'فیلم')
const seoDescription = computed(() => {
  if (movie.value?.seo_description) return movie.value.seo_description
  const base = (movie.value?.description || '').slice(0, 160)
  const bits = []
  if (castNames.value.length) bits.push(`بازیگران: ${castNames.value.join('، ')}`)
  if (downloadQualities.value.length) bits.push(`دانلود: ${downloadQualities.value.join('، ')}`)
  return `${base}${bits.length ? ` ${bits.join(' ')}` : ''}`.slice(0, 320)
})
const seoKeywords = computed(() => {
  const fromApi = movie.value?.seo_keywords || []
  const local = [
    movie.value?.title,
    movie.value?.original_title,
    movie.value?.has_downloads ? 'دانلود' : '',
    ...downloadQualities.value,
    ...castNames.value,
    ...(movie.value?.genres || []).map(genre => genre.title),
  ].filter(Boolean) as string[]
  return [...new Set([...fromApi, ...local])].join(', ')
})

useSeoMeta({
  title: seoTitle,
  description: seoDescription,
  ogTitle: seoTitle,
  ogDescription: seoDescription,
  ogImage: () => movie.value?.backdrop_url,
  twitterCard: 'summary_large_image',
  keywords: seoKeywords,
})

useHead(() => {
  const item = movie.value
  if (!item) return {}
  const site = (item.ratings || []).find(entry => entry.source === 'site' && entry.value > 0)
  return {
    script: [{
      type: 'application/ld+json',
      children: JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'Movie',
        name: item.title,
        alternateName: item.original_title,
        description: seoDescription.value,
        image: item.poster_url,
        dateCreated: item.year ? String(item.year) : undefined,
        genre: item.genres.map(genre => genre.title),
        actor: item.cast.slice(0, 10).map(person => ({ '@type': 'Person', name: person.name })),
        director: item.crew.filter(person => person.job === 'کارگردان' || person.job?.toLowerCase().includes('director')).slice(0, 3).map(person => ({
          '@type': 'Person',
          name: person.name,
        })),
        // Only website user ratings — never IMDb/TMDB as aggregateRating.
        aggregateRating: site ? {
          '@type': 'AggregateRating',
          ratingValue: site.value,
          bestRating: site.scale,
          ...(site.voteCount ? { ratingCount: site.voteCount } : {}),
        } : undefined,
        keywords: seoKeywords.value,
        ...(item.has_downloads ? {
          offers: {
            '@type': 'Offer',
            availability: 'https://schema.org/InStock',
            category: 'Download',
            name: downloadQualities.value.length
              ? `دانلود ${downloadQualities.value.join('، ')}`
              : 'دانلود مستقیم',
          },
        } : {}),
      }),
    }],
  }
})
</script>

<template>
  <!-- Single root required for Nuxt pageTransition (out-in); multi-root blanks the page. -->
  <div>
    <CatalogDetail v-if="movie" :item="movie" />
    <div v-else-if="pending" class="media-detail content-section py-10" aria-busy="true">
      <div class="mx-auto max-w-6xl space-y-5 px-4">
        <div class="h-[min(42svh,22rem)] animate-pulse rounded-[1.5rem] bg-[color:var(--surface-2,#0f1916)]" />
        <div class="h-10 w-1/3 max-w-xs animate-pulse rounded-xl bg-[color:var(--surface-3,#16241f)]" />
        <div class="h-40 animate-pulse rounded-[1.25rem] bg-[color:var(--surface-2,#0f1916)]" />
      </div>
    </div>
  </div>
</template>

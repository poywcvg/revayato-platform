<script setup lang="ts">
import { CATALOG_PAGE_SIZE, useClientPagination } from '~/composables/usePagination'

const { detail } = useActors()
const route = useRoute()
const slug = computed(() => decodeRouteSlug(route.params.slug))

const { data, pending, error, refresh } = await useAsyncData(
  () => `actor-detail-${slug.value}`,
  () => detail(slug.value),
  // Block SSR (complete HTML + SEO) but never freeze a client SPA navigation behind
  // the fetch — the template's v-if="actor" + CatalogSourceNotice cover the pending
  // state, so tapping an actor from a detail page swaps instantly.
  { watch: [slug], lazy: import.meta.client },
)

if (!pending.value && (!data.value || error.value)) {
  throw createError({ statusCode: 404, message: 'بازیگر پیدا نشد' })
}

const actor = computed(() => data.value?.actor)
const filmography = computed(() => data.value?.filmography || [])
const {
  page: filmographyPage,
  totalPages: filmographyPages,
  total: filmographyTotal,
  pageItems: filmographyPageItems,
  goToPage: goToFilmographyPage,
} = useClientPagination(filmography, CATALOG_PAGE_SIZE)

const config = useRuntimeConfig()
/** Both spellings people search: «لئوناردو دی‌کاپریو» and «Leonardo DiCaprio». */
const otherName = computed(() => {
  const value = actor.value
  if (!value) return ''
  const other = (value.secondary_name || value.original_name || '').trim()
  return other && other !== value.name ? other : ''
})
const filmographyCounts = computed(() => {
  const movies = filmography.value.filter(item => item.type === 'movie').length
  return { movies, series: filmography.value.length - movies }
})
/** «فیلم‌ها و سریال‌های X» — the words people put in front of an actor's name. */
const worksLabel = computed(() => {
  const { movies, series } = filmographyCounts.value
  return movies && series ? 'فیلم‌ها و سریال‌های' : series ? 'سریال‌های' : 'فیلم‌های'
})
const seoTitle = computed(() => {
  const value = actor.value
  if (!value) return 'بازیگر'
  return `${worksLabel.value} ${value.name}${otherName.value ? ` (${otherName.value})` : ''}`
})
const seoDescription = computed(() => {
  const value = actor.value
  const name = value?.name || 'بازیگر'
  const { movies, series } = filmographyCounts.value
  const counts = [movies ? `${movies} فیلم` : '', series ? `${series} سریال` : ''].filter(Boolean).join(' و ')
  const titles = filmography.value.slice(0, 4).map(item => item.title).filter(Boolean).join('، ')
  const lead = counts
    ? `دانلود و تماشای آنلاین ${counts} با بازی ${name}${otherName.value ? ` (${otherName.value})` : ''}`
    : `صفحه ${name} در روایتو`
  const bio = (value?.biography || '').replace(/\s+/g, ' ').trim()
  const text = [titles ? `${lead}؛ ${titles}.` : `${lead}.`, bio].filter(Boolean).join(' ')
  return text.length > 165 ? `${text.slice(0, 164).replace(/\s+\S*$/, '')}…` : text
})
const actorImage = computed(() => seoImage(config.public.siteUrl, actor.value?.photo))

useSeoMeta({
  title: seoTitle,
  description: seoDescription,
  ogTitle: seoTitle,
  ogDescription: seoDescription,
  ogType: 'profile',
  ogImage: () => actorImage.value || undefined,
  twitterImage: () => actorImage.value || undefined,
  twitterCard: 'summary_large_image',
  robots: () => (filmography.value.length ? 'index, follow, max-image-preview:large' : 'noindex, follow'),
})

useHead(() => {
  const value = actor.value
  if (!value) return {}
  const url = absoluteUrl(config.public.siteUrl, `/actors/${value.slug}`)
  return {
    script: [{
      key: 'actor-jsonld',
      type: 'application/ld+json',
      innerHTML: jsonLdString({
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': 'ProfilePage',
            '@id': `${url}#page`,
            url,
            name: seoTitle.value,
            inLanguage: 'fa-IR',
            mainEntity: {
              '@type': 'Person',
              '@id': `${url}#person`,
              name: value.name,
              ...(otherName.value ? { alternateName: otherName.value } : {}),
              ...(actorImage.value ? { image: actorImage.value } : {}),
              ...(value.biography ? { description: value.biography.slice(0, 500) } : {}),
              ...(value.birth_date ? { birthDate: value.birth_date } : {}),
              ...(value.birth_place ? { birthPlace: value.birth_place } : {}),
            },
          },
          {
            '@type': 'ItemList',
            name: seoTitle.value,
            numberOfItems: filmography.value.length,
            itemListElement: filmography.value.slice(0, 30).map((item, index) => ({
              '@type': 'ListItem',
              position: index + 1,
              url: absoluteUrl(config.public.siteUrl, detailPath(item)),
              name: item.title,
            })),
          },
          breadcrumbNode(config.public.siteUrl, [
            { name: SITE_NAME, path: '/' },
            { name: 'بازیگران', path: '/actors' },
            { name: value.name, path: `/actors/${value.slug}` },
          ]),
        ],
      }),
    }],
  }
})
</script>

<template>
  <div class="cinema-page page-section">
    <CatalogSourceNotice :error="error ? String(error.message || error) : null" :pending="pending" @retry="() => refresh()" />

    <template v-if="actor">
      <section class="page-hero relative overflow-hidden rounded-3xl p-4 sm:p-6 lg:p-8">
        <div class="grid gap-6 sm:grid-cols-[10rem_minmax(0,1fr)] lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-center lg:gap-9">
          <aside class="min-w-0">
            <div class="cinematic-card overflow-hidden rounded-2xl sm:rounded-3xl">
              <div class="cinematic-media relative aspect-[3/4]">
                <NuxtImg
                  v-if="actor.photo"
                  :src="actor.photo"
                  :alt="actor.name"
                  class="h-full w-full object-cover"
                  sizes="(max-width: 639px) 160px, (max-width: 1023px) 180px, 256px"
                />
                <span
                  v-else
                  class="theme-media-dark grid h-full w-full place-items-center bg-gradient-to-br from-primary-600 to-primary-900 text-5xl font-black text-white"
                >{{ actor.name.slice(0, 1) }}</span>
              </div>
            </div>
          </aside>

          <header class="min-w-0">
            <p class="text-xs font-black text-brand">جلوی دوربین</p>
            <h1 class="mt-1 text-[clamp(1.75rem,5vw,3rem)] font-black text-ink" dir="auto">{{ actor.name }}</h1>
            <p v-if="actor.secondary_name" class="mt-2 text-sm font-bold text-secondary" dir="rtl">{{ actor.secondary_name }}</p>
            <div v-if="actor.birth_place || actor.birth_date" class="mt-4 flex flex-wrap gap-2 text-xs font-bold text-muted">
              <span v-if="actor.birth_place" class="inline-flex min-h-9 items-center gap-1.5 rounded-xl bg-elevated px-3 ring-1 ring-line"><CinematicIcon name="globe" class="size-3.5 text-brand" />{{ actor.birth_place }}</span>
              <span v-if="actor.birth_date" class="inline-flex min-h-9 items-center gap-1.5 rounded-xl bg-elevated px-3 ring-1 ring-line"><CinematicIcon name="calendar" class="size-3.5 text-brand" />{{ actor.birth_date }}</span>
            </div>
            <p v-if="actor.biography" class="mt-5 max-w-3xl text-sm leading-8 text-secondary sm:text-base">{{ actor.biography }}</p>
            <NuxtLink to="/actors" class="ui-ghost-button mt-5 w-fit px-3 text-xs sm:text-sm">
              <CinematicIcon name="arrow-right" class="size-4" />
              همه بازیگران
            </NuxtLink>
          </header>
        </div>
      </section>

      <section class="mt-8" aria-labelledby="filmography-title">
        <SectionHeader id="filmography-title" :title="`${worksLabel} ${actor.name}`" eyebrow="آثار در روایتو" icon="film" />
        <div v-if="filmographyPageItems.length" class="catalog-grid mt-5">
          <CinematicCard v-for="item in filmographyPageItems" :key="`${item.type}-${item.id}`" :item="item" />
        </div>
        <EmptyState
          v-else
          title="هنوز اثری برای این بازیگر منتشر نشده است"
          description="با اضافه شدن عنوان‌های مرتبط، فیلم‌شناسی از همین بخش در دسترس خواهد بود."
          icon="film"
          action-label="مرور کاتالوگ"
          action-href="/movies"
        />
        <CatalogPagination
          :page="filmographyPage"
          :total-pages="filmographyPages"
          :total="filmographyTotal"
          label="صفحه‌بندی فیلم‌شناسی"
          @change="goToFilmographyPage"
        />
      </section>
    </template>
  </div>
</template>

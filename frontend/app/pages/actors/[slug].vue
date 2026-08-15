<script setup lang="ts">
import { CATALOG_PAGE_SIZE, useClientPagination } from '~/composables/usePagination'

const { detail } = useActors()
const route = useRoute()
const slug = computed(() => String(route.params.slug || ''))

const { data, pending, error, refresh } = await useAsyncData(
  () => `actor-detail-${slug.value}`,
  () => detail(slug.value),
  { watch: [slug] },
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

const seoDescription = computed(() => {
  const bio = actor.value?.biography?.slice(0, 140) || ''
  const titles = filmography.value.slice(0, 5).map(item => item.title).join('، ')
  if (bio && titles) return `${bio} آثار: ${titles}`
  if (bio) return bio
  if (titles) return `فیلم‌ها و سریال‌های ${actor.value?.name || ''}: ${titles}`
  return `صفحه ${actor.value?.name || 'بازیگر'} در روایتو`
})

useSeoMeta({
  title: () => actor.value?.name || 'بازیگر',
  description: seoDescription,
  ogTitle: () => actor.value?.name,
  ogDescription: seoDescription,
  ogImage: () => actor.value?.photo || undefined,
  twitterCard: 'summary_large_image',
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
        <SectionHeader id="filmography-title" title="فیلم‌شناسی" eyebrow="آثار در روایتو" icon="film" />
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

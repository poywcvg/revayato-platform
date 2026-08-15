<script setup lang="ts">
import type { Movie } from '~/types'
import {
  adaptApiCatalogItem,
  type ApiCatalogItem,
  type ApiListResponse,
  unwrapApiList,
} from '~/data/catalogAdapter'

const COLLECTIONS: Record<string, {
  title: string
  eyebrow: string
  description: string
  tag: string
}> = {
  marvel: {
    title: 'کالکشن مارول',
    eyebrow: 'MCU و دنیای مارول',
    description: 'فیلم‌ها و سریال‌های مارول با دوبله و زیرنویس فارسی؛ در پخش آنلاین زیرنویس نرم هم‌زمان نمایش داده می‌شود.',
    tag: 'marvel',
  },
  mcu: {
    title: 'کالکشن MCU',
    eyebrow: 'Marvel Cinematic Universe',
    description: 'عنوان‌های جهان سینمایی مارول با اولویت نسخه دوبله و زیرنویس فارسی.',
    tag: 'mcu',
  },
}

const route = useRoute()
const config = useRuntimeConfig()
const { api } = useApi()

const slug = computed(() => String(route.params.slug || '').toLowerCase())
const meta = computed(() => COLLECTIONS[slug.value] || null)

if (!meta.value) {
  throw createError({ statusCode: 404, statusMessage: 'کالکشن پیدا نشد' })
}

const { data, pending, error, refresh } = await useAsyncData(
  () => `collection-${slug.value}`,
  async () => {
    const tag = meta.value!.tag
    const mediaBase = String(config.public.mediaCdnBaseUrl)
    const [moviesRes, seriesRes] = await Promise.all([
      api<ApiListResponse<ApiCatalogItem>>('/movies/', {
        query: { tag, limit: 100, sort: 'newest' },
      }),
      api<ApiListResponse<ApiCatalogItem>>('/series/', {
        query: { tag, limit: 100, sort: 'newest' },
      }),
    ])
    const movies = unwrapApiList(moviesRes).map(item => adaptApiCatalogItem(item, 'movie', mediaBase))
    const series = unwrapApiList(seriesRes).map(item => adaptApiCatalogItem(item, 'series', mediaBase))
    const items = [...movies, ...series].sort((a, b) => {
      const yearA = Number(a.year || 0)
      const yearB = Number(b.year || 0)
      if (yearB !== yearA) return yearB - yearA
      return String(b.title || '').localeCompare(String(a.title || ''), 'fa')
    })
    return {
      items: items as Movie[],
      movies: movies as Movie[],
      series: series as Movie[],
      movieCount: movies.length,
      seriesCount: series.length,
    }
  },
  {
    watch: [slug],
    default: () => ({
      items: [] as Movie[],
      movies: [] as Movie[],
      series: [] as Movie[],
      movieCount: 0,
      seriesCount: 0,
    }),
  },
)

const items = computed(() => data.value?.items || [])
const movieCount = computed(() => data.value?.movieCount || 0)
const seriesCount = computed(() => data.value?.seriesCount || 0)
const dubbedCount = computed(() => items.value.filter(item => item.is_dubbed).length)
const subtitleCount = computed(() => items.value.filter(item => item.has_subtitle || item.is_dubbed).length)

const statsLine = computed(() => {
  const parts = [
    movieCount.value ? `${movieCount.value.toLocaleString('fa-IR')} فیلم` : '',
    seriesCount.value ? `${seriesCount.value.toLocaleString('fa-IR')} سریال` : '',
    dubbedCount.value ? `${dubbedCount.value.toLocaleString('fa-IR')} دوبله` : '',
    subtitleCount.value ? `${subtitleCount.value.toLocaleString('fa-IR')} با زیرنویس` : '',
  ].filter(Boolean)
  return parts.join(' · ')
})

useSeoMeta({
  title: meta.value.title,
  description: meta.value.description,
})
</script>

<template>
  <div class="cinema-page collection-page pb-10 sm:pb-14">
    <PageHero
      :title="meta!.title"
      :eyebrow="meta!.eyebrow"
      :description="meta!.description"
    />

    <section class="content-section">
      <p v-if="statsLine" class="mb-5 text-sm text-slate-300">
        {{ statsLine }}
      </p>

      <CatalogSourceNotice
        :error="error ? (error as any)?.message || String(error) : null"
        :pending="pending"
        @retry="() => refresh()"
      />

      <EmptyState
        v-if="!pending && !error && !items.length"
        title="هنوز عنوانی در این کالکشن نیست"
        description="در حال تکمیل آرشیو مارول هستیم. کمی بعد دوباره سر بزن."
        icon="film"
        action-label="رفتن به فیلم‌ها"
        action-href="/movies"
      />

      <MovieGrid v-else :items="items" :loading="pending" />
    </section>
  </div>
</template>

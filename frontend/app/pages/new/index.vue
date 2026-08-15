<script setup lang="ts">
import type { ContentType, CinematicIconName, Movie } from '~/types'
import {
  adaptApiCatalogItem,
  type ApiCatalogItem,
  type ApiListResponse,
  unwrapApiList,
} from '~/data/catalogAdapter'
import {
  CATALOG_PAGE_SIZE,
  clampPage,
  offsetFromPage,
  pageFromQuery,
  totalPagesFor,
} from '~/composables/usePagination'

interface RecentCatalogItem extends ApiCatalogItem {
  content_type?: ContentType
}

const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const { api } = useApi()

type RecentKind = 'all' | ContentType
const kindOptions: Array<{ label: string; value: RecentKind; icon: CinematicIconName }> = [
  { label: 'همه', value: 'all', icon: 'clapperboard' },
  { label: 'فیلم', value: 'movie', icon: 'movie' },
  { label: 'سریال', value: 'series', icon: 'series' },
]

const kind = computed<RecentKind>(() => {
  const value = String(route.query.type || 'all')
  return value === 'movie' || value === 'series' ? value : 'all'
})
const page = computed(() => pageFromQuery(route.query.page))

const { data, pending, error, refresh } = await useAsyncData(
  () => `catalog-recent-${kind.value}-${page.value}`,
  async () => {
    const response = await api<ApiListResponse<RecentCatalogItem>>('/catalog/recent/', {
      query: {
        limit: CATALOG_PAGE_SIZE,
        offset: offsetFromPage(page.value, CATALOG_PAGE_SIZE),
        ...(kind.value !== 'all' ? { type: kind.value } : {}),
      },
    })
    const mediaBase = String(config.public.mediaCdnBaseUrl)
    const items = unwrapApiList(response).map((item) => {
      const type = item.content_type === 'series' || item.content_type === 'movie'
        ? item.content_type
        : kind.value === 'series'
          ? 'series'
          : 'movie'
      return adaptApiCatalogItem(item, type, mediaBase)
    }) as Movie[]
    return {
      items,
      count: Array.isArray(response) ? items.length : Number(response.count || items.length),
    }
  },
  {
    watch: [kind, page],
    default: () => ({ items: [] as Movie[], count: 0 }),
  },
)

const items = computed(() => data.value?.items || [])
const total = computed(() => data.value?.count || 0)
const totalPages = computed(() => totalPagesFor(total.value, CATALOG_PAGE_SIZE))
const safePage = computed(() => clampPage(page.value, totalPages.value))

watch(totalPages, async (pages) => {
  if (page.value > pages) {
    await setQuery({ page: pages <= 1 ? undefined : String(pages) })
  }
})

async function setQuery(patch: Record<string, string | undefined>) {
  const query = { ...route.query } as Record<string, string | string[] | undefined>
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined || value === '' || value === 'all' || (key === 'page' && value === '1')) {
      delete query[key]
    }
    else {
      query[key] = value
    }
  }
  await router.replace({ query })
  if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
}

function setKind(value: RecentKind) {
  void setQuery({ type: value === 'all' ? undefined : value, page: undefined })
}

function goToPage(nextPage: number) {
  void setQuery({ page: nextPage <= 1 ? undefined : String(nextPage) })
}

useSeoMeta({
  title: 'تازه اضافه‌شده‌ها',
  description: 'جدیدترین فیلم‌ها و سریال‌هایی که به آرشیو روایتو اضافه شده‌اند، به‌ترتیب زمان افزودن.',
})
</script>

<template>
  <div class="page-section">
    <PageHero
      title="تازه اضافه‌شده‌ها"
      eyebrow="ورودهای جدید به آرشیو"
      description="فیلم‌ها و سریال‌هایی که به‌تازگی منتشر یا وارد کاتالوگ شده‌اند، از جدید به قدیم."
      icon="sparkles"
      :count="total"
      count-label="عنوان"
    >
      <div class="hide-scrollbar flex gap-2 overflow-x-auto pb-1">
        <button
          v-for="option in kindOptions"
          :key="option.value"
          type="button"
          class="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-bold transition"
          :class="kind === option.value
            ? 'cinema-glow bg-primary-500 text-night-950'
            : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'"
          :aria-pressed="kind === option.value"
          @click="setKind(option.value)"
        >
          <CinematicIcon
            :name="option.icon"
            class="size-4.5"
            :stroke-width="kind === option.value ? 2.2 : 1.8"
          />
          {{ option.label }}
        </button>
      </div>
    </PageHero>

    <CatalogSourceNotice
      class="mb-6"
      :error="error ? String(error.message || error) : null"
      :pending="pending"
      @retry="() => refresh()"
    />

    <div
      class="ui-surface mb-4 flex min-h-12 flex-wrap items-center justify-between gap-3 px-4 py-2.5"
      aria-live="polite"
    >
      <div class="flex min-w-0 items-center gap-2.5">
        <span class="grid size-8 shrink-0 place-items-center rounded-xl bg-primary-500/14 text-primary-300">
          <CinematicIcon name="sparkles" class="size-4.5" />
        </span>
        <p class="truncate text-sm font-black text-ink">
          {{ pending ? 'در حال بارگذاری...' : `${total.toLocaleString('fa-IR')} عنوان تازه` }}
        </p>
      </div>
      <span class="shrink-0 text-[11px] font-bold text-muted">مرتب‌شده بر اساس زمان افزودن</span>
    </div>

    <MovieGrid
      :items="items"
      :loading="pending"
      empty-title="هنوز عنوان تازه‌ای نیست"
      empty-description="با اضافه شدن فیلم و سریال جدید، این صفحه به‌روز می‌شود."
    />

    <CatalogPagination
      :page="safePage"
      :total-pages="totalPages"
      :total="total"
      :pending="pending"
      label="صفحه‌بندی تازه‌اضافه‌شده‌ها"
      @change="goToPage"
    />
  </div>
</template>

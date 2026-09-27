<script setup lang="ts">
import type { CinematicIconName, ContentType, Movie } from '~/types'
import {
  adaptApiCatalogListItem,
  type ApiCatalogItem,
  type ApiListResponse,
  unwrapApiList,
} from '~/data/catalogAdapter'

/**
 * IMDb Top 250 — films and series, in chart order.
 *
 * The API returns every chart position. A title we can already play comes as a
 * normal catalog card; a position still being completed by the crawler comes
 * with just its chart facts, and is shown as a quiet «به‌زودی» tile so the list
 * is always the real 250 — never a shorter list that pretends to be complete.
 */
interface ChartRow extends ApiCatalogItem {
  available?: boolean
  imdb_rank?: number | null
  imdb_votes?: number | null
  content_type?: ContentType
}
interface ChartResponse extends ApiListResponse<ChartRow> {
  coverage?: { total?: number, in_catalog?: number, published?: number }
}
type ChartSlot =
  | { rank: number, available: true, item: Movie }
  | { rank: number, available: false, title: string, year: number | null, rating: number | null }

const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const { api } = useApi()

const kindOptions: Array<{ label: string, value: ContentType, icon: CinematicIconName }> = [
  { label: 'فیلم', value: 'movie', icon: 'movie' },
  { label: 'سریال', value: 'series', icon: 'series' },
]
const kind = computed<ContentType>(() => (route.query.type === 'series' ? 'series' : 'movie'))
const onlyAvailable = computed(() => route.query.available === '1')

const { data, pending, error, refresh } = await useAsyncData(
  () => `imdb-top250-${kind.value}`,
  async () => {
    const response = await api<ChartResponse>('/catalog/top250/', {
      query: { type: kind.value, limit: 250 },
    })
    const mediaBase = String(config.public.mediaCdnBaseUrl)
    const slots: ChartSlot[] = unwrapApiList(response).map((row) => {
      const rank = Number(row.imdb_rank) || 0
      if (row.available && row.id != null) {
        return { rank, available: true, item: adaptApiCatalogListItem(row, kind.value, mediaBase) }
      }
      const rating = row.imdb_rating == null ? null : Number(row.imdb_rating)
      return {
        rank,
        available: false,
        title: String(row.title || row.original_title || ''),
        year: Number((row as { year?: number }).year) || null,
        rating: rating !== null && Number.isFinite(rating) ? rating : null,
      }
    })
    const coverage = (Array.isArray(response) ? undefined : response.coverage) || {}
    return { slots, coverage }
  },
  {
    watch: [kind],
    default: () => ({ slots: [] as ChartSlot[], coverage: {} as NonNullable<ChartResponse['coverage']> }),
    lazy: import.meta.client,
  },
)

const slots = computed(() => data.value?.slots || [])
const visibleSlots = computed(() => onlyAvailable.value ? slots.value.filter(slot => slot.available) : slots.value)
const readyCount = computed(() => slots.value.filter(slot => slot.available).length)
const totalCount = computed(() => Number(data.value?.coverage?.total) || slots.value.length)
const readyPercent = computed(() => totalCount.value ? Math.round((readyCount.value / totalCount.value) * 100) : 0)
const faNumber = (value: number) => value.toLocaleString('fa-IR')

async function setQuery(patch: Record<string, string | undefined>) {
  const query = { ...route.query } as Record<string, string | string[] | undefined>
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined || value === '') delete query[key]
    else query[key] = value
  }
  await router.replace({ query })
}

const kindLabel = computed(() => (kind.value === 'series' ? 'سریال' : 'فیلم'))
useSeoMeta({
  title: () => `۲۵۰ ${kindLabel.value} برتر IMDb`,
  description: () => `فهرست کامل ۲۵۰ ${kindLabel.value} برتر تاریخ به انتخاب کاربران IMDb، به ترتیب رتبه، با امکان تماشا و دانلود در روایتو.`,
})
</script>

<template>
  <div class="page-section">
    <PageHero
      title="۲۵۰ برتر IMDb"
      eyebrow="بهترین‌های تاریخ سینما و تلویزیون"
      description="فهرست رسمی ۲۵۰ فیلم و ۲۵۰ سریال برتر به رأی میلیون‌ها کاربر IMDb — هر روز به‌روز می‌شود."
      icon="trophy"
      :count="readyCount"
      count-label="آماده تماشا"
    >
      <div class="hide-scrollbar flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="نوع فهرست">
        <button
          v-for="option in kindOptions"
          :key="option.value"
          type="button"
          role="tab"
          class="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-bold transition"
          :class="kind === option.value
            ? 'cinema-glow bg-primary-500 text-night-950'
            : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'"
          :aria-selected="kind === option.value"
          @click="setQuery({ type: option.value === 'movie' ? undefined : option.value })"
        >
          <CinematicIcon :name="option.icon" class="size-4.5" :stroke-width="kind === option.value ? 2.2 : 1.8" />
          ۲۵۰ {{ option.label }} برتر
        </button>
      </div>
    </PageHero>

    <CatalogSourceNotice
      class="mb-6"
      :error="error ? String(error.message || error) : null"
      :pending="pending"
      @retry="() => refresh()"
    />

    <div class="ui-surface mb-4 flex min-h-12 flex-wrap items-center justify-between gap-3 px-4 py-2.5" aria-live="polite">
      <div class="flex min-w-0 flex-1 items-center gap-3">
        <span class="top250-seal" dir="ltr" aria-hidden="true">IMDb</span>
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-black text-ink">
            {{ pending ? 'در حال بارگذاری...' : `${faNumber(readyCount)} از ${faNumber(totalCount)} ${kindLabel} آماده تماشا` }}
          </p>
          <div
            v-if="!pending && totalCount"
            class="top250-meter mt-1.5"
            role="progressbar"
            :aria-valuenow="readyPercent"
            aria-valuemin="0"
            aria-valuemax="100"
            :aria-label="`${faNumber(readyPercent)}٪ از فهرست آماده تماشاست`"
          >
            <span :style="{ inlineSize: `${readyPercent}%` }" />
          </div>
        </div>
      </div>
      <label class="inline-flex min-h-11 shrink-0 cursor-pointer items-center gap-2 text-xs font-bold text-secondary">
        <input
          type="checkbox"
          class="size-4 accent-[var(--color-primary-500,#f5c518)]"
          :checked="onlyAvailable"
          @change="setQuery({ available: ($event.target as HTMLInputElement).checked ? '1' : undefined })"
        >
        فقط آماده تماشا
      </label>
    </div>

    <p v-if="!pending && readyCount < totalCount" class="mb-4 text-xs leading-6 text-muted">
      عنوان‌های «به‌زودی» خودکار در حال افزوده شدن‌اند؛ خزنده روایتو هر چند ساعت منبع و زیرنویس‌شان را پیدا و منتشر می‌کند.
    </p>

    <div v-if="pending && !slots.length" class="catalog-grid" aria-hidden="true">
      <div v-for="n in 12" :key="n" class="aspect-[2/3] animate-pulse rounded-[1.35rem] bg-elevated" />
    </div>

    <ol v-else class="catalog-grid" :aria-label="`۲۵۰ ${kindLabel} برتر IMDb به ترتیب رتبه`">
      <li v-for="slot in visibleSlots" :key="slot.rank" class="top250-slot min-w-0">
        <MovieCard v-if="slot.available" :item="slot.item" :priority="slot.rank <= 4" />
        <div v-else class="top250-pending" :aria-label="`رتبه ${faNumber(slot.rank)}: ${slot.title} — به‌زودی`">
          <span class="top250-pending__rank" dir="ltr">#{{ slot.rank }}</span>
          <p class="top250-pending__title" dir="ltr">{{ slot.title }}</p>
          <p class="top250-pending__meta" dir="ltr">
            <span v-if="slot.year">{{ slot.year }}</span>
            <span v-if="slot.rating" class="top250-pending__score">★ {{ slot.rating.toFixed(1) }}</span>
          </p>
          <span class="top250-pending__soon">به‌زودی</span>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.top250-seal {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  min-inline-size: 2.75rem;
  block-size: 1.75rem;
  padding-inline: 0.4rem;
  border-radius: 0.4rem;
  background: #f5c518;
  color: #0b0b0c;
  font-size: 0.75rem;
  font-weight: 900;
  letter-spacing: -0.02em;
}
.top250-meter {
  block-size: 0.3rem;
  border-radius: 999px;
  background: color-mix(in oklab, currentColor 12%, transparent);
  overflow: hidden;
}
.top250-meter > span {
  display: block;
  block-size: 100%;
  border-radius: inherit;
  background: #f5c518;
  transition: inline-size 0.6s ease;
}
.top250-slot {
  list-style: none;
}
.top250-pending {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 0.35rem;
  aspect-ratio: 2 / 3;
  padding: 0.85rem;
  border-radius: 1.35rem;
  background:
    linear-gradient(160deg, color-mix(in oklab, #f5c518 9%, transparent), transparent 55%),
    var(--color-elevated, rgb(255 255 255 / 0.04));
  box-shadow: inset 0 0 0 1px var(--color-line, rgb(255 255 255 / 0.08));
  text-align: left;
}
.top250-pending__rank {
  position: absolute;
  inset-block-start: 0.6rem;
  inset-inline-start: 0.6rem;
  font-size: clamp(1.6rem, 4vw, 2.4rem);
  font-weight: 900;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: color-mix(in oklab, #f5c518 70%, transparent);
}
.top250-pending__title {
  font-size: 0.85rem;
  font-weight: 800;
  line-height: 1.35;
  color: var(--color-ink, inherit);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.top250-pending__meta {
  display: flex;
  gap: 0.6rem;
  font-size: 0.75rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}
.top250-pending__score {
  color: #d9a900;
}
.top250-pending__soon {
  align-self: flex-end;
  margin-block-start: 0.25rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 800;
  background: color-mix(in oklab, currentColor 10%, transparent);
  opacity: 0.8;
}
@media (prefers-reduced-motion: reduce) {
  .top250-meter > span { transition: none; }
}
</style>

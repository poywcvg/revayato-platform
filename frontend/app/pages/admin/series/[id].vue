<script setup lang="ts">
/**
 * Edit one series.
 *
 * Same shape as the film editor: the save is a PATCH of just the changed fields
 * so a TMDB sync is not frozen out of everything else on the page, and playback
 * sources are handled by the shared `RvMediaDesk`.
 *
 * What differs is the model. A series is a span of years rather than one date,
 * carries a production status the catalog filters on, and — unlike a film — its
 * sources are episode-level. That last one is why the desk matters more here:
 * «سریال منبع دارد» is almost never the question, «کدام قسمت خراب است» is, and
 * the desk answers it per episode.
 */
import type { AdminSeries } from '~/types/admin'
import ArrowRight from '~icons/lucide/arrow-right'
import Save from '~icons/lucide/save'
import RefreshCw from '~icons/lucide/refresh-cw'
import Tv from '~icons/lucide/tv'
import Info from '~icons/lucide/info'
import Image from '~icons/lucide/image'
import Loader from '~icons/lucide/loader-circle'
import ExternalLink from '~icons/lucide/external-link'

definePageMeta({ layout: 'admin', middleware: 'staff' })

const route = useRoute()
const router = useRouter()
const { api } = useApi()
const notify = useNotifications()

const seriesId = computed(() => Number(route.params.id))
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

const { data, pending, error, refresh } = await useAsyncData(
  () => `admin-series-${seriesId.value}`,
  () => api<AdminSeries>(`/admin/series/${seriesId.value}/`),
  { watch: [seriesId] },
)

useSeoMeta({ title: () => `ویرایش ${data.value?.title || 'سریال'} — روایتو` })

type Draft = Pick<AdminSeries,
  'title' | 'original_title' | 'slug' | 'short_description' | 'description'
  | 'start_year' | 'end_year' | 'status' | 'age_rating' | 'content_format'
  | 'language' | 'imdb_id' | 'tmdb_id' | 'poster_external_url'
  | 'backdrop_external_url' | 'trailer_external_url' | 'is_published'
  | 'is_featured' | 'is_dubbed' | 'has_subtitle'
>

const FIELDS: (keyof Draft)[] = [
  'title', 'original_title', 'slug', 'short_description', 'description',
  'start_year', 'end_year', 'status', 'age_rating', 'content_format',
  'language', 'imdb_id', 'tmdb_id', 'poster_external_url',
  'backdrop_external_url', 'trailer_external_url', 'is_published',
  'is_featured', 'is_dubbed', 'has_subtitle',
]

function draftFrom(series: AdminSeries | null | undefined): Draft {
  const source = (series || {}) as Partial<AdminSeries>
  return Object.fromEntries(FIELDS.map(key => [key, source[key] ?? ''])) as Draft
}

const draft = ref<Draft>(draftFrom(data.value))
watch(data, series => { draft.value = draftFrom(series) }, { immediate: true })

const changed = computed(() => {
  const server = draftFrom(data.value)
  const payload: Record<string, unknown> = {}
  for (const key of FIELDS) {
    const next = draft.value[key]
    if (String(next ?? '') !== String(server[key] ?? '')) payload[key] = next === '' ? null : next
  }
  return payload
})
const dirty = computed(() => Object.keys(changed.value).length > 0)

const saving = ref(false)
async function save() {
  if (!dirty.value) return
  saving.value = true
  try {
    await api(`/admin/series/${seriesId.value}/`, { method: 'PATCH', body: changed.value })
    notify.success('ذخیره شد', 'تغییرات اعمال شد')
    await refresh()
  }
  catch (err) {
    const detail = (err as { data?: Record<string, string[] | string> })?.data
    const first = detail && typeof detail === 'object'
      ? Object.entries(detail).map(([k, v]) => `${k}: ${Array.isArray(v) ? v[0] : v}`)[0]
      : ''
    notify.error('ذخیره نشد', first || 'اعتبارسنجی ناموفق بود')
  }
  finally { saving.value = false }
}

onBeforeRouteLeave(() => {
  if (!dirty.value) return true
  return window.confirm('تغییرات ذخیره‌نشده از بین می‌رود. خارج می‌شوید؟')
})

const syncing = ref(false)
async function syncFromTmdb() {
  syncing.value = true
  try {
    await api(`/admin/series/${seriesId.value}/sync-tmdb/`, { method: 'POST' })
    notify.success('هم‌گام شد', 'اطلاعات از TMDB به‌روزرسانی شد')
    await refresh()
  }
  catch { notify.error('خطا', 'هم‌گام‌سازی با TMDB ناموفق بود') }
  finally { syncing.value = false }
}

/** The desk rewrites links, publication state and flags; re-read the record. */
function onDeskChanged() {
  void refresh()
}

const STATUS_OPTIONS = [
  { value: 'ongoing', label: 'در حال پخش' },
  { value: 'ended', label: 'پایان یافته' },
  { value: 'upcoming', label: 'به‌زودی' },
  { value: 'cancelled', label: 'لغو شده' },
  { value: 'on_hold', label: 'متوقف' },
]
const FORMAT_OPTIONS = [
  { value: 'live_action', label: 'واقعی' },
  { value: 'animation', label: 'انیمیشن' },
  { value: 'short', label: 'کوتاه' },
]
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9 !px-2.5" aria-label="بازگشت" @click="router.back()">
          <ArrowRight class="size-4" />
        </button>
        <div class="min-w-0">
          <h1 class="truncate text-xl font-black text-[var(--rv-text)]">{{ data?.title || 'ویرایش سریال' }}</h1>
          <p class="mt-0.5 text-xs font-semibold text-[var(--rv-muted)]">
            شناسه {{ fa(seriesId) }}<span v-if="data?.slug"> · {{ data.slug }}</span>
          </p>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <a
          v-if="data?.slug"
          :href="`/series/${data.slug}`"
          target="_blank"
          rel="noopener"
          class="rv-btn rv-btn--subtle rv-focus"
        >
          <ExternalLink class="size-4" /> مشاهده
        </a>
        <button type="button" class="rv-btn rv-btn--ghost rv-focus" :disabled="syncing" @click="syncFromTmdb">
          <Loader v-if="syncing" class="size-4 animate-spin" />
          <RefreshCw v-else class="size-4" />
          هم‌گام با TMDB
        </button>
        <button type="button" class="rv-btn rv-btn--primary rv-focus" :disabled="!dirty || saving" @click="save">
          <Loader v-if="saving" class="size-4 animate-spin" />
          <Save v-else class="size-4" />
          ذخیره
        </button>
      </div>
    </div>

    <RvState v-if="error" kind="error" title="سریال خوانده نشد" @retry="refresh()" />
    <div v-else-if="pending && !data" class="h-64 animate-pulse rounded-[var(--rv-radius)] bg-[var(--rv-surface-3)]" />

    <template v-else-if="data">
      <div class="grid gap-5 lg:grid-cols-3">
        <div class="space-y-5 lg:col-span-2">
          <RvPanel :icon="Info" title="اطلاعات اصلی">
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="block">
                <span class="rv-label">عنوان فارسی</span>
                <input v-model="draft.title" type="text" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">عنوان اصلی</span>
                <input v-model="draft.original_title" type="text" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block sm:col-span-2">
                <span class="rv-label">نامک (slug)</span>
                <input v-model="draft.slug" type="text" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block sm:col-span-2">
                <span class="rv-label">توضیح کوتاه</span>
                <input v-model="draft.short_description" type="text" class="rv-input mt-1.5">
              </label>
              <label class="block sm:col-span-2">
                <span class="rv-label">خلاصه داستان</span>
                <textarea v-model="draft.description" rows="5" class="rv-input mt-1.5" />
              </label>
            </div>
          </RvPanel>

          <RvPanel :icon="Tv" title="مشخصات">
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="block">
                <span class="rv-label">سال شروع</span>
                <input v-model.number="draft.start_year" type="number" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">سال پایان</span>
                <input v-model.number="draft.end_year" type="number" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">وضعیت پخش</span>
                <select v-model="draft.status" class="rv-input mt-1.5">
                  <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
              </label>
              <label class="block">
                <span class="rv-label">قالب</span>
                <select v-model="draft.content_format" class="rv-input mt-1.5">
                  <option v-for="o in FORMAT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
              </label>
              <label class="block">
                <span class="rv-label">رده سنی</span>
                <input v-model="draft.age_rating" type="text" dir="ltr" class="rv-input mt-1.5" placeholder="TV-MA">
              </label>
              <label class="block">
                <span class="rv-label">زبان</span>
                <input v-model="draft.language" type="text" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">IMDb ID</span>
                <input v-model="draft.imdb_id" type="text" dir="ltr" class="rv-input mt-1.5" placeholder="tt0000000">
              </label>
              <label class="block">
                <span class="rv-label">TMDB ID</span>
                <input v-model.number="draft.tmdb_id" type="number" dir="ltr" class="rv-input mt-1.5">
              </label>
            </div>
          </RvPanel>

          <RvPanel :icon="Image" title="تصاویر و تریلر">
            <div class="grid gap-4">
              <label class="block">
                <span class="rv-label">نشانی پوستر</span>
                <input v-model="draft.poster_external_url" type="url" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">نشانی تصویر پس‌زمینه</span>
                <input v-model="draft.backdrop_external_url" type="url" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">نشانی تریلر</span>
                <input v-model="draft.trailer_external_url" type="url" dir="ltr" class="rv-input mt-1.5">
              </label>
            </div>
          </RvPanel>

          <!-- Links, probes, gaps, viewer reports and per-episode state. -->
          <RvMediaDesk :id="seriesId" kind="series" @changed="onDeskChanged" />
        </div>

        <div class="space-y-5">
          <RvPanel title="وضعیت انتشار">
            <div class="space-y-4">
              <label class="flex items-center justify-between gap-3">
                <span class="text-xs font-bold text-[var(--rv-text)]">منتشر شده</span>
                <input v-model="draft.is_published" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              </label>
              <label class="flex items-center justify-between gap-3">
                <span class="text-xs font-bold text-[var(--rv-text)]">ویژه</span>
                <input v-model="draft.is_featured" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              </label>
              <label class="flex items-center justify-between gap-3">
                <span class="text-xs font-bold text-[var(--rv-text)]">دوبله فارسی</span>
                <input v-model="draft.is_dubbed" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              </label>
              <label class="flex items-center justify-between gap-3">
                <span class="text-xs font-bold text-[var(--rv-text)]">زیرنویس</span>
                <input v-model="draft.has_subtitle" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              </label>
            </div>
          </RvPanel>

          <RvPanel title="اطلاعات سامانه">
            <dl class="space-y-2.5 text-xs font-bold">
              <div class="flex justify-between gap-3">
                <dt class="text-[var(--rv-muted)]">منبع اطلاعات</dt>
                <dd class="text-[var(--rv-text)]">{{ data.metadata_source || '—' }}</dd>
              </div>
              <div class="flex justify-between gap-3">
                <dt class="text-[var(--rv-muted)]">امتیاز IMDb</dt>
                <dd class="text-[var(--rv-text)]">{{ data.imdb_rating || '—' }}</dd>
              </div>
              <div class="flex justify-between gap-3">
                <dt class="text-[var(--rv-muted)]">آرا</dt>
                <dd class="text-[var(--rv-text)]">{{ fa(data.vote_count) }}</dd>
              </div>
            </dl>
          </RvPanel>
        </div>
      </div>
    </template>
  </div>
</template>

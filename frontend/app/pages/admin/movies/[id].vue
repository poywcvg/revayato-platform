<script setup lang="ts">
/**
 * Edit one film.
 *
 * The movies list could publish, feature and archive — every verb except the
 * one people actually needed, which was changing what a title *says*. A wrong
 * Persian title or a missing year had to be fixed in Django admin or not at
 * all.
 *
 * Saving sends only what changed, because writing a field marks it as a manual
 * override that future TMDB syncs must not touch; a full-object PUT would
 * silently freeze every field on the page.
 *
 * Playback sources used to be read-only here, on the reasoning that every link
 * on the site had passed the verification gate and a pasted URL would be the one
 * that hadn't. The reasoning was right and the conclusion was wrong: it left an
 * admin able to see a dead mirror and unable to remove it. `RvMediaDesk` makes
 * them editable through the same identity classifier and normalizer the importer
 * uses, so a hand-added link is held to the crawler's standard instead of being
 * forbidden outright.
 */
import type { AdminMovie } from '~/types/admin'
import ArrowRight from '~icons/lucide/arrow-right'
import Save from '~icons/lucide/save'
import RefreshCw from '~icons/lucide/refresh-cw'
import Film from '~icons/lucide/film'
import Info from '~icons/lucide/info'
import Image from '~icons/lucide/image'
import Loader from '~icons/lucide/loader-circle'
import ExternalLink from '~icons/lucide/external-link'

definePageMeta({ layout: 'admin', middleware: 'staff' })

const route = useRoute()
const router = useRouter()
const { api } = useApi()
const notify = useNotifications()

const movieId = computed(() => Number(route.params.id))
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

const { data, pending, error, refresh } = await useAsyncData(
  () => `admin-movie-${movieId.value}`,
  () => api<AdminMovie>(`/admin/movies/${movieId.value}/`),
  { watch: [movieId] },
)

useSeoMeta({ title: () => `ویرایش ${data.value?.title || 'فیلم'} — روایتو` })

/** The editable subset, kept apart from the server object so `dirty` is honest. */
type Draft = Pick<AdminMovie,
  'title' | 'original_title' | 'slug' | 'short_description' | 'description'
  | 'release_date' | 'release_year' | 'duration_minutes' | 'catalog_type'
  | 'publication_status' | 'age_rating' | 'content_format' | 'language'
  | 'imdb_id' | 'tmdb_id' | 'poster_external_url' | 'backdrop_external_url'
  | 'trailer_external_url' | 'is_featured' | 'is_recommended' | 'featured_order'
  | 'slider_platform' | 'is_dubbed'
  | 'has_subtitle' | 'meta_title' | 'meta_description'
>

const FIELDS: (keyof Draft)[] = [
  'title', 'original_title', 'slug', 'short_description', 'description',
  'release_date', 'release_year', 'duration_minutes', 'catalog_type',
  'publication_status', 'age_rating', 'content_format', 'language',
  'imdb_id', 'tmdb_id', 'poster_external_url', 'backdrop_external_url',
  'trailer_external_url', 'is_featured', 'is_recommended', 'featured_order',
  'slider_platform', 'is_dubbed',
  'has_subtitle', 'meta_title', 'meta_description',
]

function draftFrom(movie: AdminMovie | null | undefined): Draft {
  const source = (movie || {}) as Partial<AdminMovie>
  return Object.fromEntries(FIELDS.map(key => [key, source[key] ?? ''])) as Draft
}

const draft = ref<Draft>(draftFrom(data.value))
watch(data, movie => { draft.value = draftFrom(movie) }, { immediate: true })

/** Numbers and dates clear to null; a cleared text field must stay '' (the API rejects null there). */
const NULLABLE = new Set<string>(['release_date', 'release_year', 'duration_minutes', 'tmdb_id', 'imdb_id'])
/** Numeric slider order clears to 0 (first), never to an empty string the API would reject. */
const NUMERIC_ZERO = new Set<string>(['featured_order'])

/** Only what actually changed. See the note on manual overrides above. */
const changed = computed(() => {
  const server = draftFrom(data.value)
  const payload: Record<string, unknown> = {}
  for (const key of FIELDS) {
    const next = draft.value[key]
    if (String(next ?? '') !== String(server[key] ?? '')) {
      if (next === '' && NULLABLE.has(key)) payload[key] = null
      else if (NUMERIC_ZERO.has(key)) payload[key] = Number(next) || 0
      else payload[key] = next
    }
  }
  return payload
})
const dirty = computed(() => Object.keys(changed.value).length > 0)

const saving = ref(false)
async function save() {
  if (!dirty.value) return
  saving.value = true
  try {
    await api(`/admin/movies/${movieId.value}/`, { method: 'PATCH', body: changed.value, timeout: 30_000 })
    notify.success('ذخیره شد', 'تغییرات اعمال شد')
    await refresh()
  }
  catch (err) {
    notify.error('ذخیره نشد', adminErrorMessage(err, 'اعتبارسنجی ناموفق بود'))
  }
  finally { saving.value = false }
}

// Leaving with unsaved edits is almost always a mis-click, not a decision.
onBeforeRouteLeave(() => {
  if (!dirty.value) return true
  return window.confirm('تغییرات ذخیره‌نشده از بین می‌رود. خارج می‌شوید؟')
})

const syncing = ref(false)
async function syncFromTmdb() {
  syncing.value = true
  try {
    // TMDB detail + Persian translation takes 4–10s; the shared 10s ceiling aborted it.
    await api(`/admin/movies/${movieId.value}/sync-tmdb/`, { method: 'POST', timeout: 60_000 })
    notify.success('هم‌گام شد', 'اطلاعات از TMDB به‌روزرسانی شد')
    await refresh()
  }
  catch (err) { notify.error('هم‌گام‌سازی با TMDB نشد', adminErrorMessage(err)) }
  finally { syncing.value = false }
}

/** The desk rewrites links, publication state and flags; re-read the record. */
function onDeskChanged() {
  void refresh()
}

const STATUS_OPTIONS = [
  { value: 'published', label: 'منتشر شده' },
  { value: 'draft', label: 'پیش‌نویس' },
  { value: 'archived', label: 'بایگانی' },
]
const TYPE_OPTIONS = [
  { value: 'movie', label: 'فیلم' },
  { value: 'documentary', label: 'مستند' },
  { value: 'short', label: 'کوتاه' },
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
          <h1 class="truncate text-xl font-black text-[var(--rv-text)]">{{ data?.title || 'ویرایش فیلم' }}</h1>
          <p class="mt-0.5 text-xs font-semibold text-[var(--rv-muted)]">
            شناسه {{ fa(movieId) }}<span v-if="data?.slug"> · {{ data.slug }}</span>
          </p>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <a
          v-if="data?.slug"
          :href="`/movies/${data.slug}`"
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

    <RvState v-if="error" kind="error" title="فیلم خوانده نشد" @retry="refresh()" />
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
                <textarea v-model="draft.description" rows="5" class="rv-input mt-1.5 !h-auto resize-y" />
              </label>
            </div>
          </RvPanel>

          <RvPanel :icon="Film" title="مشخصات">
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="block">
                <span class="rv-label">تاریخ اکران</span>
                <input v-model="draft.release_date" type="date" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">سال</span>
                <input v-model.number="draft.release_year" type="number" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">مدت (دقیقه)</span>
                <input v-model.number="draft.duration_minutes" type="number" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">رده سنی</span>
                <input v-model="draft.age_rating" type="text" dir="ltr" class="rv-input mt-1.5" placeholder="PG-13">
              </label>
              <label class="block">
                <span class="rv-label">نوع</span>
                <select v-model="draft.catalog_type" class="rv-input mt-1.5">
                  <option v-for="o in TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
              </label>
              <label class="block">
                <span class="rv-label">قالب</span>
                <select v-model="draft.content_format" class="rv-input mt-1.5">
                  <option v-for="o in FORMAT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
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

          <!-- The operations desk. Everything about playability — links,
               subtitles, probes, gaps, viewer reports, crawler runs and the
               audit trail — lives in one component shared with the series page. -->
          <RvMediaDesk :id="movieId" kind="movie" @changed="onDeskChanged" />
        </div>

        <div class="space-y-5">
          <RvPanel title="وضعیت انتشار">
            <div class="space-y-4">
              <label class="block">
                <span class="rv-label">وضعیت</span>
                <select v-model="draft.publication_status" class="rv-input mt-1.5">
                  <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
              </label>
              <label class="flex items-center justify-between gap-3">
                <span class="text-xs font-bold text-[var(--rv-text)]">ویژه (اسلایدر خانه)</span>
                <input v-model="draft.is_featured" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              </label>
              <label class="block">
                <span class="rv-label">ترتیب اسلایدر (کمتر = اول‌تر)</span>
                <input v-model.number="draft.featured_order" type="number" min="0" max="9999" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">نمایش اسلایدر در</span>
                <select v-model="draft.slider_platform" class="rv-input mt-1.5">
                  <option value="all">وب‌سایت و اپلیکیشن</option>
                  <option value="web">فقط وب‌سایت</option>
                  <option value="app">فقط اپلیکیشن</option>
                </select>
              </label>
              <label class="flex items-center justify-between gap-3">
                <span class="text-xs font-bold text-[var(--rv-text)]">پیشنهادی</span>
                <input v-model="draft.is_recommended" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
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

          <RvPanel title="سئو">
            <div class="space-y-4">
              <label class="block">
                <span class="rv-label">عنوان متا</span>
                <input v-model="draft.meta_title" type="text" class="rv-input mt-1.5">
              </label>
              <label class="block">
                <span class="rv-label">توضیح متا</span>
                <textarea v-model="draft.meta_description" rows="3" class="rv-input mt-1.5 !h-auto resize-y" />
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
              <div v-if="data.manual_override_fields?.length" class="pt-1">
                <dt class="text-[var(--rv-muted)]">ویرایش دستی</dt>
                <dd class="mt-1.5 flex flex-wrap gap-1">
                  <RvBadge v-for="field in data.manual_override_fields" :key="field" tone="violet">{{ field }}</RvBadge>
                </dd>
              </div>
            </dl>
          </RvPanel>
        </div>
      </div>
    </template>
  </div>
</template>

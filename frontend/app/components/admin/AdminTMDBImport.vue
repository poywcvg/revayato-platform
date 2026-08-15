<script setup lang="ts">
import ArrowRight from '~icons/lucide/arrow-right'
import Check from '~icons/lucide/circle-check'
import ExternalLink from '~icons/lucide/external-link'
import Film from '~icons/lucide/film'
import Hash from '~icons/lucide/hash'
import Loader from '~icons/lucide/loader-circle'
import Search from '~icons/lucide/search'
import Shield from '~icons/lucide/shield-check'
import Star from '~icons/lucide/star'
import TriangleAlert from '~icons/lucide/triangle-alert'
import Tv from '~icons/lucide/tv'
import type {
  AppErrorDetails,
  TMDBContentType,
  TMDBImportResponse,
  TMDBPreview,
  TMDBSearchMovie,
} from '~/types'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; imported: [response: TMDBImportResponse] }>()
const adminApi = useAdminMovies()
const notifications = useNotifications()

type EntryMode = 'search' | 'id'
type Step = 'browse' | 'preview' | 'success'

const step = ref<Step>('browse')
const entryMode = ref<EntryMode>('search')
const contentType = ref<TMDBContentType>('movie')
const searchQuery = ref('')
const searchResults = ref<TMDBSearchMovie[]>([])
const searchTotal = ref(0)
const searching = ref(false)
const searchTried = ref(false)
const tmdbId = ref('')
const selected = ref<TMDBPreview | null>(null)
const imported = ref<TMDBImportResponse | null>(null)
const previewing = ref(false)
const importing = ref(false)
const error = ref<AppErrorDetails | null>(null)
const linkedMovieId = ref<number | undefined>()
const publicationChoice = ref<'draft' | 'published'>('draft')
const searchInput = useTemplateRef<HTMLInputElement>('searchInput')
const idInput = useTemplateRef<HTMLInputElement>('idInput')

let searchTimer: ReturnType<typeof setTimeout> | undefined

const numericTmdbId = computed(() => {
  const value = Number(String(tmdbId.value).trim())
  return Number.isFinite(value) ? value : 0
})
const validTmdbId = computed(() => Number.isSafeInteger(numericTmdbId.value) && numericTmdbId.value > 0)
const director = computed(() => selected.value?.crew.find(item => item.job === 'Director')?.name)
const contentLabel = computed(() => contentType.value === 'movie' ? 'فیلم' : 'سریال')
const busy = computed(() => previewing.value || importing.value || searching.value)
const canArchiveExisting = computed(() => Boolean(
  contentType.value === 'movie' && selected.value?.local_movie?.id && selected.value.already_imported,
))

watch(() => props.open, async (open) => {
  if (!open) {
    clearTimeout(searchTimer)
    return
  }
  reset()
  await nextTick()
  focusActiveInput()
})

watch(entryMode, async () => {
  error.value = null
  await nextTick()
  focusActiveInput()
})

watch(contentType, () => {
  error.value = null
  selected.value = null
  if (contentType.value === 'series' && entryMode.value === 'search') {
    entryMode.value = 'id'
  }
})

watch(searchQuery, (value) => {
  clearTimeout(searchTimer)
  error.value = null
  if (contentType.value !== 'movie') return
  const query = value.trim()
  if (query.length < 2) {
    searchResults.value = []
    searchTotal.value = 0
    searchTried.value = false
    searching.value = false
    return
  }
  searchTimer = setTimeout(() => {
    void runSearch(query)
  }, 350)
})

onBeforeUnmount(() => clearTimeout(searchTimer))

function focusActiveInput() {
  if (entryMode.value === 'search') searchInput.value?.focus()
  else idInput.value?.focus()
}

function reset() {
  clearTimeout(searchTimer)
  step.value = 'browse'
  entryMode.value = 'search'
  contentType.value = 'movie'
  searchQuery.value = ''
  searchResults.value = []
  searchTotal.value = 0
  searchTried.value = false
  searching.value = false
  tmdbId.value = ''
  selected.value = null
  imported.value = null
  previewing.value = false
  importing.value = false
  error.value = null
  linkedMovieId.value = undefined
  publicationChoice.value = 'draft'
}

function backToBrowse() {
  step.value = 'browse'
  selected.value = null
  error.value = null
  linkedMovieId.value = undefined
  nextTick().then(focusActiveInput)
}

async function runSearch(query = searchQuery.value.trim()) {
  if (contentType.value !== 'movie') return
  if (query.length < 2) return
  searching.value = true
  searchTried.value = true
  error.value = null
  try {
    const response = await adminApi.tmdbSearch(query)
    searchResults.value = response.results
    searchTotal.value = response.total_results
  }
  catch (cause) {
    searchResults.value = []
    searchTotal.value = 0
    error.value = getAppError(cause, 'جستجوی TMDB انجام نشد.')
  }
  finally {
    searching.value = false
  }
}

async function loadPreview(id?: number) {
  const targetId = id ?? numericTmdbId.value
  if (!Number.isSafeInteger(targetId) || targetId <= 0) {
    error.value = getAppError(null, 'شناسه TMDB باید یک عدد صحیح بزرگ‌تر از صفر باشد.')
    return
  }
  previewing.value = true
  error.value = null
  try {
    selected.value = contentType.value === 'movie'
      ? await adminApi.tmdbPreview(targetId)
      : await adminApi.tmdbSeriesPreview(targetId)
    linkedMovieId.value = contentType.value === 'movie'
      ? selected.value.local_movie?.id
      : undefined
    if (!tmdbId.value) tmdbId.value = String(targetId)
    step.value = 'preview'
  }
  catch (cause) {
    error.value = getAppError(cause, `اطلاعات ${contentLabel.value} با این TMDB ID دریافت نشد.`)
  }
  finally {
    previewing.value = false
  }
}

async function importContent() {
  if (!selected.value) return
  importing.value = true
  error.value = null
  try {
    const publish = publicationChoice.value === 'published'
    const response = contentType.value === 'movie'
      ? await adminApi.tmdbImport(selected.value.tmdb_id, {
          link_movie_id: linkedMovieId.value,
          publish,
        })
      : await adminApi.tmdbSeriesImport(selected.value.tmdb_id)
    imported.value = response
    step.value = 'success'
    emit('imported', response)
    if (publish && response.published) {
      notifications.success(`${contentLabel.value} منتشر شد`, 'عنوان در سایت قابل مشاهده است.')
    }
    else if (publish && !response.published) {
      notifications.warning(
        'به‌صورت پیش‌نویس ذخیره شد',
        'برای انتشار، رسانه و حقوق باید کامل باشد؛ فعلاً پیش‌نویس ثبت شد.',
      )
    }
    else {
      notifications.success(
        `${contentLabel.value} اضافه شد`,
        `${contentLabel.value} به‌صورت پیش‌نویس ثبت شد و آماده بازبینی است.`,
      )
    }
  }
  catch (cause) {
    error.value = getAppError(cause, `افزودن ${contentLabel.value} انجام نشد.`)
  }
  finally {
    importing.value = false
  }
}

async function archiveExisting() {
  const movieId = selected.value?.local_movie?.id
  if (!movieId) return
  importing.value = true
  error.value = null
  try {
    await adminApi.archive(movieId)
    notifications.success('فیلم حذف شد', 'فیلم از نمایش عمومی خارج و آرشیو شد.')
    emit('imported', { created: false, published: false, movie: { id: movieId } } as TMDBImportResponse)
    emit('close')
  }
  catch (cause) {
    error.value = getAppError(cause, 'حذف فیلم انجام نشد.')
  }
  finally {
    importing.value = false
  }
}

function yearOf(value?: string) {
  return value?.slice(0, 4) || '—'
}
</script>

<template>
  <AdminModal
    :open="open"
    title="افزودن از TMDB"
    description="نام فیلم را جستجو کنید یا شناسه TMDB را مستقیم وارد کنید."
    size="xl"
    :closeable="!busy"
    @close="$emit('close')"
  >
    <div class="border-b border-[var(--admin-border)] bg-[var(--admin-surface)] px-5 py-3 sm:px-6">
      <ol class="flex flex-wrap items-center gap-2 text-[11px] font-extrabold sm:text-xs">
        <li :class="step === 'browse' ? 'text-[var(--admin-primary)]' : 'text-[var(--admin-muted)]'">۱. انتخاب عنوان</li>
        <li class="text-[var(--admin-border)]">/</li>
        <li :class="step === 'preview' ? 'text-[var(--admin-primary)]' : 'text-[var(--admin-muted)]'">۲. بازبینی</li>
        <li class="text-[var(--admin-border)]">/</li>
        <li :class="step === 'success' ? 'text-[var(--admin-primary)]' : 'text-[var(--admin-muted)]'">۳. نتیجه</li>
      </ol>
    </div>

    <div v-if="step === 'browse'" class="p-5 sm:p-6">
      <div class="mx-auto max-w-3xl space-y-5">
        <fieldset>
          <legend class="mb-3 text-sm font-black">نوع محتوا</legend>
          <div class="grid grid-cols-2 gap-3">
            <label
              class="admin-focus flex cursor-pointer items-center gap-3 rounded-2xl border p-4"
              :class="contentType === 'movie' ? 'border-[var(--admin-primary)] bg-[var(--admin-primary)]/8 text-[var(--admin-primary)]' : 'border-[var(--admin-border)] bg-white text-[var(--admin-muted)]'"
            >
              <input v-model="contentType" type="radio" value="movie" class="sr-only">
              <Film class="size-5" />
              <span class="font-black">فیلم</span>
              <Check v-if="contentType === 'movie'" class="mr-auto size-4" />
            </label>
            <label
              class="admin-focus flex cursor-pointer items-center gap-3 rounded-2xl border p-4"
              :class="contentType === 'series' ? 'border-[var(--admin-primary)] bg-[var(--admin-primary)]/8 text-[var(--admin-primary)]' : 'border-[var(--admin-border)] bg-white text-[var(--admin-muted)]'"
            >
              <input v-model="contentType" type="radio" value="series" class="sr-only">
              <Tv class="size-5" />
              <span class="font-black">سریال</span>
              <Check v-if="contentType === 'series'" class="mr-auto size-4" />
            </label>
          </div>
        </fieldset>

        <div
          v-if="contentType === 'movie'"
          class="grid grid-cols-2 gap-1 rounded-2xl bg-[var(--admin-surface-muted)] p-1"
          role="tablist"
          aria-label="روش افزودن"
        >
          <button
            type="button"
            role="tab"
            class="admin-focus inline-flex min-h-11 items-center justify-center gap-2 rounded-xl text-sm font-extrabold"
            :class="entryMode === 'search' ? 'bg-white text-[var(--admin-primary)] shadow-sm' : 'text-[var(--admin-muted)]'"
            :aria-selected="entryMode === 'search'"
            @click="entryMode = 'search'"
          >
            <Search class="size-4" /> جستجو با نام
          </button>
          <button
            type="button"
            role="tab"
            class="admin-focus inline-flex min-h-11 items-center justify-center gap-2 rounded-xl text-sm font-extrabold"
            :class="entryMode === 'id' ? 'bg-white text-[var(--admin-primary)] shadow-sm' : 'text-[var(--admin-muted)]'"
            :aria-selected="entryMode === 'id'"
            @click="entryMode = 'id'"
          >
            <Hash class="size-4" /> شناسه TMDB
          </button>
        </div>

        <div v-if="contentType === 'movie' && entryMode === 'search'" class="space-y-4">
          <label class="block">
            <span class="mb-1.5 block text-xs font-extrabold">جستجوی فیلم در TMDB</span>
            <div class="relative">
              <Search class="pointer-events-none absolute right-4 top-1/2 size-5 -translate-y-1/2 text-[var(--admin-accent)]" />
              <input
                ref="searchInput"
                v-model="searchQuery"
                type="search"
                class="admin-focus h-14 w-full rounded-2xl border border-[var(--admin-border)] bg-white pr-12 pl-12 text-sm outline-none placeholder:text-[var(--admin-muted)]/55 focus:border-[var(--admin-accent)]"
                placeholder="مثلاً تلقین، جدایی نادر از سیمین…"
                aria-label="جستجوی فیلم در TMDB"
                autocomplete="off"
              >
              <Loader v-if="searching" class="absolute left-4 top-1/2 size-5 -translate-y-1/2 animate-spin text-[var(--admin-accent)]" />
            </div>
            <span class="mt-1.5 block text-[11px] leading-5 text-[var(--admin-muted)]">حداقل ۲ حرف بنویسید؛ نتایج لحظه‌ای از TMDB می‌آید.</span>
          </label>

          <div v-if="searching && !searchResults.length" class="grid min-h-40 place-items-center rounded-2xl border border-dashed border-[var(--admin-border)] bg-white text-sm text-[var(--admin-muted)]">
            در حال جستجو…
          </div>
          <div v-else-if="searchTried && !searchResults.length" class="grid min-h-40 place-items-center rounded-2xl border border-dashed border-[var(--admin-border)] bg-white px-4 text-center text-sm text-[var(--admin-muted)]">
            نتیجه‌ای پیدا نشد. املا را عوض کنید یا با شناسه TMDB ادامه دهید.
          </div>
          <div v-else-if="searchResults.length" class="space-y-2">
            <p class="text-xs font-bold text-[var(--admin-muted)]">
              {{ Math.min(searchResults.length, searchTotal).toLocaleString('fa-IR') }}
              نتیجه
              <span v-if="searchTotal > searchResults.length">از {{ searchTotal.toLocaleString('fa-IR') }}</span>
            </p>
            <ul class="max-h-[min(48dvh,420px)] space-y-2 overflow-y-auto rounded-2xl border border-[var(--admin-border)] bg-white p-2">
              <li v-for="item in searchResults" :key="item.tmdb_id">
                <button
                  type="button"
                  class="admin-focus flex w-full items-start gap-3 rounded-xl p-2.5 text-right hover:bg-[var(--admin-surface-muted)]"
                  :disabled="previewing"
                  @click="loadPreview(item.tmdb_id)"
                >
                  <div class="h-[4.5rem] w-12 shrink-0 overflow-hidden rounded-lg bg-[var(--admin-surface-muted)]">
                    <img v-if="item.poster_url" :src="item.poster_url" :alt="`پوستر ${item.title}`" class="h-full w-full object-cover" loading="lazy">
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <p class="truncate font-black text-[var(--admin-text)]">{{ item.title }}</p>
                      <AdminBadge v-if="item.already_imported" tone="warning">ثبت‌شده</AdminBadge>
                    </div>
                    <p class="mt-0.5 truncate text-xs text-[var(--admin-muted)]" dir="ltr">{{ item.original_title }}</p>
                    <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--admin-muted)]">
                      <span>{{ yearOf(item.release_date) }}</span>
                      <span v-if="item.vote_average" class="inline-flex items-center gap-1 font-bold" dir="ltr">
                        <Star class="size-3 fill-amber-400 text-amber-500" />
                        {{ Number(item.vote_average).toFixed(1) }}
                      </span>
                      <span class="font-latin">TMDB {{ item.tmdb_id }}</span>
                    </div>
                    <p v-if="item.overview" class="mt-2 line-clamp-2 text-[11px] leading-5 text-[var(--admin-muted)]">{{ item.overview }}</p>
                  </div>
                </button>
              </li>
            </ul>
          </div>
          <div v-else class="rounded-2xl border border-dashed border-[var(--admin-border)] bg-white p-5 text-sm leading-7 text-[var(--admin-muted)]">
            نام فارسی یا انگلیسی فیلم را بنویسید تا فهرست نتایج نمایش داده شود.
          </div>
        </div>

        <form v-else class="space-y-4" @submit.prevent="loadPreview()">
          <AdminField
            label="TMDB ID"
            required
            :hint="contentType === 'series' ? 'برای سریال فعلاً فقط با شناسه TMDB می‌توانید اضافه کنید.' : 'عدد انتهای آدرس عنوان در سایت TMDB را وارد کنید.'"
          >
            <div class="relative">
              <Hash class="pointer-events-none absolute right-4 top-1/2 size-5 -translate-y-1/2 text-[var(--admin-accent)]" />
              <input
                ref="idInput"
                v-model="tmdbId"
                type="text"
                inputmode="numeric"
                pattern="[0-9]*"
                dir="ltr"
                class="admin-focus h-14 w-full rounded-2xl border border-[var(--admin-border)] bg-white pr-12 pl-4 font-latin text-lg font-bold outline-none placeholder:text-[var(--admin-muted)]/45 focus:border-[var(--admin-accent)]"
                placeholder="مثلاً 550"
                aria-label="شناسه TMDB"
              >
            </div>
          </AdminField>
          <AdminButton class="w-full justify-center" type="submit" :loading="previewing" :disabled="!validTmdbId">
            دریافت اطلاعات {{ contentLabel }}
          </AdminButton>
        </form>

        <UiErrorAlert v-if="error" :error="error" @close="error = null" />

        <div class="flex items-start gap-3 rounded-2xl bg-[var(--admin-surface-muted)] p-4 text-xs leading-6 text-[var(--admin-muted)]">
          <Shield class="mt-0.5 size-5 shrink-0 text-emerald-700" />
          ژانرها با فهرست فارسی سایت یکی هستند. هنگام افزودن می‌توانید پیش‌نویس، انتشار یا حذف عنوان موجود را انتخاب کنید.
        </div>
      </div>
    </div>

    <div v-else-if="step === 'preview' && selected" class="p-5 sm:p-6">
      <button
        type="button"
        class="admin-focus mb-4 inline-flex items-center gap-2 rounded-lg px-2 py-1 text-xs font-bold text-[var(--admin-accent)] hover:bg-[var(--admin-surface-muted)]"
        :disabled="importing"
        @click="backToBrowse"
      >
        <ArrowRight class="size-4" /> بازگشت به انتخاب
      </button>

      <div class="overflow-hidden rounded-[22px] border border-[var(--admin-border)] bg-[var(--admin-surface)]">
        <div class="relative h-40 bg-[var(--admin-sidebar)] sm:h-52">
          <img v-if="selected.backdrop_url" :src="selected.backdrop_url" :alt="`تصویر پس‌زمینه ${selected.title}`" class="h-full w-full object-cover opacity-70">
          <div class="absolute inset-0 bg-gradient-to-t from-[var(--admin-sidebar)]/80 to-[var(--admin-sidebar)]/20" />
        </div>
        <div class="relative grid gap-5 p-5 sm:grid-cols-[140px_1fr] sm:p-6">
          <div class="-mt-20 aspect-[2/3] w-28 overflow-hidden rounded-2xl border-4 border-white bg-[var(--admin-surface-muted)] shadow-xl sm:-mt-24 sm:w-auto">
            <img v-if="selected.poster_url" :src="selected.poster_url" :alt="`پوستر ${selected.title}`" class="h-full w-full object-cover">
          </div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-start gap-2">
              <div class="min-w-0 flex-1">
                <h3 class="text-xl font-black sm:text-2xl">{{ selected.title }}</h3>
                <p class="mt-1 font-latin text-sm text-[var(--admin-muted)]">{{ selected.original_title }}</p>
              </div>
              <AdminBadge tone="tmdb">{{ contentLabel }} · TMDB {{ selected.tmdb_id }}</AdminBadge>
              <AdminBadge v-if="selected.already_imported" tone="warning">قبلاً ثبت شده</AdminBadge>
            </div>
            <div class="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--admin-muted)]">
              <span>{{ selected.release_date || 'تاریخ نامشخص' }}</span>
              <span v-if="selected.runtime">{{ selected.runtime }} دقیقه</span>
              <span v-if="selected.imdb_rating" class="inline-flex items-center gap-1 font-bold" dir="ltr">
                <Star class="size-3.5 fill-amber-400 text-amber-500" />
                IMDb {{ Number(selected.imdb_rating).toFixed(1) }}
              </span>
              <span v-else-if="selected.vote_average" class="inline-flex items-center gap-1 font-bold" dir="ltr">
                <Star class="size-3.5 fill-amber-400 text-amber-500" />
                TMDB {{ selected.vote_average.toFixed(1) }}
              </span>
              <span v-if="selected.certification">رده {{ selected.certification }}</span>
              <span v-if="contentType === 'series'">
                {{ (selected.season_count || 0).toLocaleString('fa-IR') }} فصل ·
                {{ (selected.episode_count || 0).toLocaleString('fa-IR') }} قسمت
              </span>
            </div>
            <p class="mt-4 text-sm leading-7 text-[var(--admin-muted)]">{{ selected.overview || 'خلاصه‌ای برای این عنوان موجود نیست.' }}</p>
            <div class="mt-4 flex flex-wrap gap-1.5">
              <span
                v-for="genre in selected.genres"
                :key="genre.id"
                class="rounded-lg bg-[var(--admin-surface-muted)] px-2.5 py-1 text-[11px] font-bold text-[var(--admin-primary)]"
              >
                {{ genre.name }}
              </span>
            </div>
            <dl class="mt-5 grid gap-3 text-xs sm:grid-cols-3">
              <div>
                <dt class="text-[var(--admin-muted)]">{{ contentType === 'movie' ? 'کارگردان' : 'سازنده/کارگردان' }}</dt>
                <dd class="mt-1 font-bold">{{ director || 'ثبت نشده' }}</dd>
              </div>
              <div>
                <dt class="text-[var(--admin-muted)]">شناسه IMDb</dt>
                <dd class="mt-1 font-latin font-bold">{{ selected.imdb_id || '—' }}</dd>
              </div>
              <div>
                <dt class="text-[var(--admin-muted)]">تریلر</dt>
                <dd class="mt-1 font-bold">{{ selected.trailer_youtube_key ? 'موجود' : 'ثبت نشده' }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>

      <div v-if="contentType === 'movie' && selected.duplicates.length" class="mt-4 rounded-2xl border border-amber-300 bg-amber-50 p-4">
        <div class="flex gap-3">
          <TriangleAlert class="mt-0.5 size-5 shrink-0 text-amber-700" />
          <div class="min-w-0 flex-1">
            <h4 class="font-black text-amber-900">احتمال تکراری بودن</h4>
            <p class="mt-1 text-xs leading-6 text-amber-800">اگر این عنوان همان مورد موجود است، آن را برای اتصال به TMDB انتخاب کنید.</p>
            <div class="mt-3 space-y-2">
              <label
                v-for="duplicate in selected.duplicates"
                :key="duplicate.id"
                class="flex cursor-pointer items-center gap-3 rounded-xl border border-amber-200 bg-white p-3"
              >
                <input v-model="linkedMovieId" type="radio" :value="duplicate.id" class="accent-[var(--admin-primary)]">
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-bold">{{ duplicate.title }} ({{ duplicate.release_year || '—' }})</p>
                  <p class="font-latin text-[10px] text-[var(--admin-muted)]">TMDB {{ duplicate.tmdb_id || '—' }} · IMDb {{ duplicate.imdb_id || '—' }}</p>
                </div>
                <NuxtLink
                  :to="`/admin/movies/${duplicate.id}/edit`"
                  class="admin-focus inline-flex items-center gap-1 text-xs font-bold text-[var(--admin-primary)]"
                  @click.stop
                >
                  <ExternalLink class="size-3.5" /> باز کردن
                </NuxtLink>
              </label>
            </div>
          </div>
        </div>
      </div>

      <UiErrorAlert v-if="error" class="mt-4" :error="error" @close="error = null" />

      <div class="mt-5 rounded-2xl border border-[var(--admin-border)] bg-[var(--admin-surface)] p-4">
        <h4 class="text-sm font-black">وضعیت پس از افزودن</h4>
        <p class="mt-1 text-xs leading-6 text-[var(--admin-muted)]">انتخاب کنید فیلم به‌صورت پیش‌نویس بماند یا همان لحظه در سایت منتشر شود.</p>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <label
            class="admin-focus cursor-pointer rounded-2xl border p-4"
            :class="publicationChoice === 'draft' ? 'border-[var(--admin-primary)] bg-[var(--admin-primary)]/8' : 'border-[var(--admin-border)] bg-white'"
          >
            <input v-model="publicationChoice" type="radio" value="draft" class="sr-only">
            <span class="text-sm font-black">پیش‌نویس</span>
            <span class="mt-1 block text-xs text-[var(--admin-muted)]">فقط در پنل ادمین دیده می‌شود.</span>
          </label>
          <label
            class="admin-focus cursor-pointer rounded-2xl border p-4"
            :class="publicationChoice === 'published' ? 'border-emerald-500 bg-emerald-50' : 'border-[var(--admin-border)] bg-white'"
          >
            <input v-model="publicationChoice" type="radio" value="published" class="sr-only" :disabled="contentType !== 'movie'">
            <span class="text-sm font-black">منتشر در سایت</span>
            <span class="mt-1 block text-xs text-[var(--admin-muted)]">
              {{ contentType === 'movie' ? 'اگر متادیتا کامل باشد، در کاتالوگ عمومی نمایش داده می‌شود.' : 'انتشار مستقیم سریال فعلاً پشتیبانی نمی‌شود.' }}
            </span>
          </label>
        </div>
        <button
          v-if="canArchiveExisting"
          type="button"
          class="admin-focus mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 text-xs font-extrabold text-[var(--admin-danger)] hover:bg-red-100 disabled:opacity-50"
          :disabled="importing"
          @click="archiveExisting"
        >
          حذف از سایت (آرشیو عنوان موجود)
        </button>
      </div>
    </div>

    <div v-else-if="step === 'success'" class="grid min-h-[420px] place-items-center p-6 text-center">
      <div class="max-w-md">
        <span class="mx-auto grid size-16 place-items-center rounded-2xl bg-emerald-100 text-emerald-700">
          <Check class="size-8" />
        </span>
        <h3 class="mt-5 text-2xl font-black">{{ contentLabel }} اضافه شد</h3>
        <p class="mt-2 text-sm leading-7 text-[var(--admin-muted)]">
          {{ imported?.published
            ? 'عنوان منتشر شد و در سایت قابل مشاهده است.'
            : 'اطلاعات TMDB دریافت شد و عنوان به‌صورت پیش‌نویس آماده بازبینی است.' }}
        </p>
        <div class="mt-6 flex flex-col justify-center gap-2 sm:flex-row">
          <NuxtLink v-if="imported?.movie?.id" :to="`/admin/movies/${imported.movie.id}/edit`">
            <AdminButton class="w-full justify-center sm:w-auto">
              <template #icon><Film class="size-4" /></template>
              باز کردن ویرایشگر فیلم
            </AdminButton>
          </NuxtLink>
          <NuxtLink v-else-if="imported?.series?.id" :to="`/admin/series/${imported.series.id}/edit`">
            <AdminButton class="w-full justify-center sm:w-auto">
              <template #icon><Tv class="size-4" /></template>
              باز کردن ویرایشگر سریال
            </AdminButton>
          </NuxtLink>
          <AdminButton variant="secondary" class="w-full justify-center sm:w-auto" @click="reset">
            افزودن عنوان دیگر
          </AdminButton>
        </div>
      </div>
    </div>

    <template v-if="step === 'preview'" #footer>
      <div class="flex flex-col-reverse gap-3 sm:flex-row sm:items-center">
        <div class="flex items-center gap-2 text-xs text-[var(--admin-muted)]">
          <Shield class="size-4 text-emerald-700" />
          {{ publicationChoice === 'published' ? 'پس از افزودن، در صورت کامل بودن اطلاعات منتشر می‌شود.' : 'ثبت اولیه به‌صورت پیش‌نویس خواهد بود.' }}
        </div>
        <div class="flex flex-wrap gap-2 sm:mr-auto">
          <AdminButton variant="ghost" :disabled="importing" @click="backToBrowse">بازگشت</AdminButton>
          <AdminButton
            v-if="canArchiveExisting"
            variant="secondary"
            :disabled="importing"
            class="text-[var(--admin-danger)]"
            @click="archiveExisting"
          >
            حذف
          </AdminButton>
          <AdminButton :loading="importing" @click="importContent">
            {{ publicationChoice === 'published' ? `افزودن و انتشار ${contentLabel}` : `افزودن به‌صورت پیش‌نویس` }}
          </AdminButton>
        </div>
      </div>
    </template>
  </AdminModal>
</template>

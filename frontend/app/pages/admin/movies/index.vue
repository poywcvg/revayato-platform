<script setup lang="ts">
import Archive from '~icons/lucide/archive'
import ClipboardList from '~icons/lucide/clipboard-list'
import Film from '~icons/lucide/film'
import Grid from '~icons/lucide/grid-2x2'
import List from '~icons/lucide/list'
import Plus from '~icons/lucide/plus'
import Refresh from '~icons/lucide/rotate-cw'
import Search from '~icons/lucide/search'
import Sparkles from '~icons/lucide/sparkles'
import type { AdminGenre, AdminMovie, AdminMovieFilters, AdminMovieListResponse, AppErrorDetails, TMDBImportResponse } from '~/types'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'مدیریت فیلم‌ها', robots: 'noindex, nofollow' })

const route = useRoute()
const router = useRouter()
const adminApi = useAdminMovies()
const notifications = useNotifications()
const movies = ref<AdminMovie[]>([])
const genres = ref<AdminGenre[]>([])
const total = ref(0)
const loading = ref(true)
const actionLoading = ref(false)
const error = ref<AppErrorDetails | null>(null)
const view = ref<'table' | 'grid'>('table')
const tmdbOpen = ref(route.query.tmdb === '1')
const archiveTarget = ref<AdminMovie | null>(null)
const syncTarget = ref<AdminMovie | null>(null)
const syncDryRun = ref<TMDBImportResponse | null>(null)
const syncOverwrite = ref(false)
const pageSize = 20
const page = ref(Math.max(1, Number(route.query.page) || 1))
const filters = reactive<AdminMovieFilters>({
  q: String(route.query.q || ''),
  status: (route.query.status as AdminMovieFilters['status']) || '',
  source: (route.query.source as AdminMovieFilters['source']) || '',
  type: (route.query.type as AdminMovieFilters['type']) || '',
  genre: String(route.query.genre || ''),
  year: String(route.query.year || ''),
  ordering: String(route.query.ordering || '-updated_at'),
  limit: pageSize,
  offset: (page.value - 1) * pageSize,
})
let filterTimer: ReturnType<typeof setTimeout> | undefined

const hasActiveFilters = computed(() => Boolean(filters.q || filters.status || filters.source || filters.genre || filters.year))
const publishedOnPage = computed(() => movies.value.filter(movie => movie.publication_status === 'published').length)
const draftOnPage = computed(() => movies.value.filter(movie => movie.publication_status === 'draft').length)

const statusOptions = [
  { value: '', label: 'همه وضعیت‌ها' },
  { value: 'draft', label: 'پیش‌نویس' },
  { value: 'published', label: 'منتشرشده' },
  { value: 'archived', label: 'آرشیوشده' },
]
const sourceOptions = [
  { value: '', label: 'همه منابع' },
  { value: 'tmdb', label: 'متصل به TMDB' },
  { value: 'manual', label: 'ثبت دستی' },
]
const orderingOptions = [
  { value: '-updated_at', label: 'آخرین ویرایش' },
  { value: '-created_at', label: 'جدیدترین ثبت' },
  { value: '-release_date', label: 'تاریخ انتشار' },
  { value: '-rating_average', label: 'بالاترین امتیاز' },
  { value: '-popularity', label: 'محبوب‌ترین' },
]
const yearOptions = computed(() => [
  { value: '', label: 'همه سال‌ها' },
  ...Array.from({ length: 40 }, (_, i) => {
    const year = String(new Date().getFullYear() + 1 - i)
    return { value: year, label: year }
  }),
])

const selectClass = 'admin-focus h-11 w-full min-w-0 rounded-xl border border-[var(--admin-border)] bg-white px-3 text-xs font-bold outline-none focus:border-[var(--admin-accent)]'

onMounted(() => {
  if (!import.meta.client) return
  const saved = window.localStorage.getItem('admin-movies-view')
  if (saved === 'table' || saved === 'grid') view.value = saved
  if (window.matchMedia('(max-width: 767px)').matches && !saved) view.value = 'grid'
})

watch(view, (value) => {
  if (import.meta.client) window.localStorage.setItem('admin-movies-view', value)
})

async function loadMovies() {
  loading.value = true
  error.value = null
  filters.offset = (page.value - 1) * pageSize
  try {
    const response: AdminMovieListResponse = await adminApi.list(filters)
    movies.value = response.results
    total.value = response.count
  }
  catch (cause) {
    error.value = getAppError(cause, 'فهرست فیلم‌ها دریافت نشد.')
  }
  finally {
    loading.value = false
  }
}

async function loadGenres() {
  try {
    genres.value = await adminApi.genres()
  }
  catch {
    genres.value = []
  }
}

function syncQuery() {
  router.replace({
    query: {
      ...(filters.q && { q: filters.q }),
      ...(filters.status && { status: filters.status }),
      ...(filters.source && { source: filters.source }),
      ...(filters.type && { type: filters.type }),
      ...(filters.genre && { genre: filters.genre }),
      ...(filters.year && { year: filters.year }),
      ...(filters.ordering !== '-updated_at' && { ordering: filters.ordering }),
      ...(page.value > 1 && { page: String(page.value) }),
      ...(tmdbOpen.value && { tmdb: '1' }),
    },
  })
}

function clearFilters() {
  Object.assign(filters, {
    q: '',
    status: '',
    source: '',
    genre: '',
    year: '',
    ordering: '-updated_at',
  })
}

watch(() => [filters.q, filters.status, filters.source, filters.type, filters.genre, filters.year, filters.ordering], () => {
  clearTimeout(filterTimer)
  page.value = 1
  filterTimer = setTimeout(() => {
    syncQuery()
    void loadMovies()
  }, filters.q ? 400 : 80)
})

onBeforeUnmount(() => clearTimeout(filterTimer))
watch(page, () => {
  syncQuery()
  void loadMovies()
})
watch(() => route.query.tmdb, (value) => {
  if (value === '1') tmdbOpen.value = true
})

function edit(movie: AdminMovie) {
  navigateTo(`/admin/movies/${movie.id}/edit`)
}

function preview(movie: AdminMovie) {
  if (movie.publication_status === 'published') {
    window.open(`/movies/${movie.slug}`, '_blank', 'noopener,noreferrer')
  }
  else {
    edit(movie)
  }
}

function closeTmdb() {
  tmdbOpen.value = false
  const query = { ...route.query }
  delete query.tmdb
  router.replace({ query })
}

function imported() {
  void loadMovies()
}

async function confirmArchive() {
  if (!archiveTarget.value) return
  actionLoading.value = true
  try {
    await adminApi.archive(archiveTarget.value.id)
    notifications.success('فیلم حذف شد', 'فیلم از نمایش عمومی خارج شد و در آرشیو باقی ماند.')
    archiveTarget.value = null
    await loadMovies()
  }
  catch (cause) {
    notifications.notifyError(cause, 'حذف انجام نشد')
  }
  finally {
    actionLoading.value = false
  }
}

async function setStatus(movie: AdminMovie, status: 'draft' | 'published') {
  actionLoading.value = true
  try {
    await adminApi.setPublicationStatus(movie.id, status)
    notifications.success(
      status === 'published' ? 'فیلم منتشر شد' : 'فیلم به پیش‌نویس برگشت',
      status === 'published'
        ? 'عنوان در سایت قابل مشاهده است؛ خزنده Film2Media (myf2m) لینک‌های دانلود و پخش آنلاین را در پس‌زمینه پیدا می‌کند.'
        : 'عنوان فقط در پنل ادمین دیده می‌شود.',
    )
    await loadMovies()
  }
  catch (cause) {
    notifications.notifyError(cause, 'تغییر وضعیت انجام نشد')
  }
  finally {
    actionLoading.value = false
  }
}

async function openSync(movie: AdminMovie) {
  syncTarget.value = movie
  syncDryRun.value = null
  syncOverwrite.value = false
  actionLoading.value = true
  try {
    syncDryRun.value = await adminApi.sync(movie.id, { dry_run: true, overwrite_manual: false })
  }
  catch (cause) {
    notifications.notifyError(cause, 'پیش‌نمایش همگام‌سازی آماده نشد')
    syncTarget.value = null
  }
  finally {
    actionLoading.value = false
  }
}

async function confirmSync() {
  if (!syncTarget.value) return
  actionLoading.value = true
  try {
    const response = await adminApi.sync(syncTarget.value.id, { overwrite_manual: syncOverwrite.value })
    notifications.success(
      'همگام‌سازی کامل شد',
      response.skipped_manual_fields.length
        ? `${response.skipped_manual_fields.length.toLocaleString('fa-IR')} فیلد دستی محافظت شد.`
        : 'اطلاعات TMDB با موفقیت به‌روزرسانی شد.',
    )
    syncTarget.value = null
    await loadMovies()
  }
  catch (cause) {
    notifications.notifyError(cause, 'همگام‌سازی انجام نشد')
  }
  finally {
    actionLoading.value = false
  }
}

await Promise.all([loadMovies(), loadGenres()])
</script>

<template>
  <div class="px-4 py-5 sm:px-6 sm:py-7 lg:px-8 lg:py-9">
    <header class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div class="min-w-0">
        <div class="mb-2 flex flex-wrap items-center gap-2 text-xs font-bold text-[var(--admin-muted)]">
          <span>استودیو روایتو</span>
          <span>/</span>
          <span class="text-[var(--admin-primary)]">فیلم‌ها</span>
        </div>
        <h1 class="text-2xl font-black tracking-tight sm:text-3xl">مدیریت فیلم‌ها</h1>
        <p class="mt-2 max-w-2xl text-sm leading-7 text-[var(--admin-muted)]">
          جستجو کنید، از TMDB اضافه کنید، یا عنوان را دستی ثبت و منتشر کنید.
        </p>
      </div>
      <div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
        <AdminButton class="w-full justify-center sm:w-auto" variant="secondary" @click="navigateTo('/admin/movies/new')">
          <template #icon><Plus class="size-4" /></template>
          افزودن دستی
        </AdminButton>
        <AdminButton class="w-full justify-center sm:w-auto" @click="tmdbOpen = true">
          <template #icon><Sparkles class="size-4" /></template>
          افزودن از TMDB
        </AdminButton>
      </div>
    </header>

    <div class="mt-6 grid gap-3 sm:mt-7 sm:grid-cols-3">
      <div class="rounded-2xl border border-[var(--admin-border)] bg-[var(--admin-surface)] p-4 shadow-[var(--admin-shadow)]">
        <div class="flex items-center justify-between gap-3">
          <p class="text-xs font-bold text-[var(--admin-muted)]">کل نتایج</p>
          <span class="grid size-9 place-items-center rounded-xl bg-[var(--admin-primary)]/10 text-[var(--admin-primary)]"><Film class="size-4" /></span>
        </div>
        <p class="mt-2 font-latin text-2xl font-black text-[var(--admin-primary)]">{{ total.toLocaleString('fa-IR') }}</p>
      </div>
      <div class="rounded-2xl border border-[var(--admin-border)] bg-[var(--admin-surface)] p-4 shadow-[var(--admin-shadow)]">
        <div class="flex items-center justify-between gap-3">
          <p class="text-xs font-bold text-[var(--admin-muted)]">منتشرشده در این صفحه</p>
          <span class="grid size-9 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><ClipboardList class="size-4" /></span>
        </div>
        <p class="mt-2 font-latin text-2xl font-black text-emerald-700">{{ publishedOnPage.toLocaleString('fa-IR') }}</p>
      </div>
      <div class="rounded-2xl border border-[var(--admin-border)] bg-[var(--admin-surface)] p-4 shadow-[var(--admin-shadow)]">
        <div class="flex items-center justify-between gap-3">
          <p class="text-xs font-bold text-[var(--admin-muted)]">نیازمند بازبینی</p>
          <span class="grid size-9 place-items-center rounded-xl bg-amber-50 text-amber-700"><Search class="size-4" /></span>
        </div>
        <p class="mt-2 font-latin text-2xl font-black text-amber-700">{{ draftOnPage.toLocaleString('fa-IR') }}</p>
      </div>
    </div>

    <AdminCard class="mt-5 overflow-hidden">
      <div class="sticky top-14 z-20 border-b border-[var(--admin-border)] bg-[var(--admin-surface)]/95 p-4 backdrop-blur-md sm:p-5 lg:top-0">
        <div class="grid gap-3 lg:grid-cols-[minmax(240px,1.5fr)_repeat(4,minmax(0,1fr))] lg:items-end">
          <label class="relative block">
            <span class="mb-1.5 block text-[11px] font-extrabold text-[var(--admin-muted)]">جستجو</span>
            <span class="relative block">
              <Search class="pointer-events-none absolute right-3.5 top-1/2 size-4.5 -translate-y-1/2 text-[var(--admin-accent)]" />
              <input
                v-model="filters.q"
                type="search"
                class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white pr-10 pl-3 text-sm outline-none placeholder:text-[var(--admin-muted)]/70 focus:border-[var(--admin-accent)]"
                placeholder="عنوان، IMDb یا شناسه TMDB…"
                aria-label="جستجوی فیلم‌ها"
              >
            </span>
          </label>
          <label>
            <span class="mb-1.5 block text-[11px] font-extrabold text-[var(--admin-muted)]">وضعیت</span>
            <select v-model="filters.status" :class="selectClass"><option v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select>
          </label>
          <label>
            <span class="mb-1.5 block text-[11px] font-extrabold text-[var(--admin-muted)]">منبع</span>
            <select v-model="filters.source" :class="selectClass"><option v-for="option in sourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select>
          </label>
          <label>
            <span class="mb-1.5 block text-[11px] font-extrabold text-[var(--admin-muted)]">ژانر</span>
            <select v-model="filters.genre" :class="selectClass"><option value="">همه ژانرها</option><option v-for="genre in genres" :key="genre.id" :value="genre.slug">{{ genre.title }}</option></select>
          </label>
          <label>
            <span class="mb-1.5 block text-[11px] font-extrabold text-[var(--admin-muted)]">سال</span>
            <select v-model="filters.year" :class="selectClass"><option v-for="option in yearOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select>
          </label>
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-2 sm:gap-3">
          <label class="flex min-h-11 w-full items-center gap-2 sm:w-auto">
            <span class="text-[11px] font-extrabold text-[var(--admin-muted)]">مرتب‌سازی</span>
            <select v-model="filters.ordering" class="admin-focus h-11 min-w-0 flex-1 rounded-lg border border-[var(--admin-border)] bg-white px-3 text-[11px] font-bold outline-none focus:border-[var(--admin-accent)] sm:flex-none">
              <option v-for="option in orderingOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>

          <button
            v-if="hasActiveFilters"
            type="button"
            class="admin-focus inline-flex min-h-11 items-center rounded-lg px-2 text-xs font-bold text-[var(--admin-accent)] hover:underline"
            @click="clearFilters"
          >
            پاک کردن فیلترها
          </button>

          <div class="ms-auto flex items-center gap-2">
            <button
              type="button"
              class="admin-focus inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2.5 text-xs font-bold text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)]"
              :disabled="loading"
              @click="loadMovies"
            >
              <Refresh class="size-3.5" :class="loading && 'animate-spin'" />
              به‌روزرسانی
            </button>
            <div class="flex min-h-11 rounded-xl border border-[var(--admin-border)] bg-[var(--admin-surface-muted)] p-0.5" role="group" aria-label="نوع نمایش">
              <button type="button" class="admin-focus grid size-10 place-items-center rounded-lg" :class="view === 'table' ? 'bg-white text-[var(--admin-primary)] shadow-sm' : 'text-[var(--admin-muted)]'" aria-label="نمای جدول" :aria-pressed="view === 'table'" @click="view = 'table'"><List class="size-4" /></button>
              <button type="button" class="admin-focus grid size-10 place-items-center rounded-lg" :class="view === 'grid' ? 'bg-white text-[var(--admin-primary)] shadow-sm' : 'text-[var(--admin-muted)]'" aria-label="نمای کارت" :aria-pressed="view === 'grid'" @click="view = 'grid'"><Grid class="size-4" /></button>
            </div>
          </div>
        </div>
      </div>

      <AdminState
        v-if="error && !loading"
        kind="error"
        title="فهرست فیلم‌ها در دسترس نیست"
        :message="error.message"
        @retry="loadMovies"
      />
      <AdminState
        v-else-if="!loading && !movies.length"
        :title="hasActiveFilters ? 'فیلمی با این فیلتر پیدا نشد' : 'هنوز فیلمی ثبت نشده است'"
        :message="hasActiveFilters ? 'فیلترها را تغییر دهید یا عبارت کوتاه‌تری جستجو کنید.' : 'از TMDB اضافه کنید یا یک عنوان را دستی ثبت کنید.'"
      >
        <div class="flex flex-col items-center justify-center gap-2 sm:flex-row">
          <AdminButton variant="secondary" @click="navigateTo('/admin/movies/new')">افزودن دستی</AdminButton>
          <AdminButton @click="tmdbOpen = true">افزودن از TMDB</AdminButton>
        </div>
      </AdminState>
      <AdminMovieTable
        v-else-if="view === 'table'"
        :movies="movies"
        :loading="loading"
        @edit="edit"
        @preview="preview"
        @sync="openSync"
        @publish="setStatus($event, 'published')"
        @draft="setStatus($event, 'draft')"
        @archive="archiveTarget = $event"
      />
      <div v-else-if="loading" class="grid gap-4 p-5 [grid-template-columns:repeat(auto-fill,minmax(min(100%,8rem),1fr))]">
        <div v-for="i in 10" :key="i" class="aspect-[2/3] animate-pulse rounded-2xl bg-[var(--admin-surface-muted)]" />
      </div>
      <AdminMovieGrid
        v-else
        :movies="movies"
        @edit="edit"
        @preview="preview"
        @sync="openSync"
        @publish="setStatus($event, 'published')"
        @draft="setStatus($event, 'draft')"
        @archive="archiveTarget = $event"
      />

      <AdminPagination
        v-if="total"
        :page="page"
        :total="total"
        :page-size="pageSize"
        :loading="loading"
        count-label=" فیلم"
        @update:page="page = $event"
      />
    </AdminCard>

    <AdminTMDBImport :open="tmdbOpen" @close="closeTmdb" @imported="imported" />
    <AdminConfirmDialog
      :open="Boolean(archiveTarget)"
      title="حذف فیلم از سایت؟"
      :message="`«${archiveTarget?.title || ''}» از سایت عمومی خارج می‌شود، اما اطلاعات آن در آرشیو باقی می‌ماند.`"
      confirm-label="حذف از سایت"
      dangerous
      :loading="actionLoading"
      @close="archiveTarget = null"
      @confirm="confirmArchive"
    >
      <div class="mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-xs font-bold text-[var(--admin-danger)]">
        <Archive class="size-4" /> این عملیات حذف دائمی از پایگاه‌داده نیست.
      </div>
    </AdminConfirmDialog>

    <AdminModal
      :open="Boolean(syncTarget)"
      title="همگام‌سازی با TMDB"
      :description="`اطلاعات «${syncTarget?.title || ''}» ابتدا به‌صورت dry-run بررسی شده است.`"
      size="sm"
      :closeable="!actionLoading"
      @close="syncTarget = null"
    >
      <div class="p-6">
        <div v-if="actionLoading && !syncDryRun" class="py-8 text-center text-sm text-[var(--admin-muted)]">در حال بررسی تغییرات…</div>
        <template v-else>
          <div class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs leading-6 text-emerald-900">
            <strong class="block text-sm">اطلاعات دستی محافظت می‌شود</strong>
            {{ (syncDryRun?.skipped_manual_fields.length || 0).toLocaleString('fa-IR') }} فیلد دستی در این همگام‌سازی بازنویسی نخواهد شد.
          </div>
          <label class="mt-4 flex cursor-pointer gap-3 rounded-2xl border border-red-200 bg-red-50/60 p-4">
            <input v-model="syncOverwrite" type="checkbox" class="mt-1 accent-[var(--admin-danger)]">
            <span class="text-xs leading-6 text-[var(--admin-danger)]">
              <strong class="block text-sm">بازنویسی اطلاعات دستی</strong>
              این گزینه ممکن است اصلاحات تیم محتوا را با داده TMDB جایگزین کند.
            </span>
          </label>
        </template>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <AdminButton variant="ghost" :disabled="actionLoading" @click="syncTarget = null">انصراف</AdminButton>
          <AdminButton :loading="actionLoading" @click="confirmSync">همگام‌سازی</AdminButton>
        </div>
      </template>
    </AdminModal>
  </div>
</template>

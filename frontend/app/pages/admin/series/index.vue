<script setup lang="ts">
import Plus from '~icons/lucide/plus'
import Refresh from '~icons/lucide/rotate-cw'
import Search from '~icons/lucide/search'
import Tv from '~icons/lucide/tv'
import type { AdminGenre, AdminSeries, AdminSeriesFilters, AdminSeriesListResponse, AppErrorDetails, TMDBImportResponse } from '~/types'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'مدیریت سریال‌ها', robots: 'noindex, nofollow' })

const route = useRoute()
const adminApi = useAdminSeries()
const notifications = useNotifications()
const seriesList = ref<AdminSeries[]>([])
const genres = ref<AdminGenre[]>([])
const total = ref(0)
const loading = ref(true)
const actionLoading = ref(false)
const error = ref<AppErrorDetails | null>(null)
const pageSize = 20
const {
  filters,
  page,
  debouncedWatch,
  syncQuery,
  clearFilters,
} = useDebouncedFilters<AdminSeriesFilters>({
  q: String(route.query.q || ''),
  status: (route.query.status as AdminSeriesFilters['status']) || '',
  source: (route.query.source as AdminSeriesFilters['source']) || '',
  genre: String(route.query.genre || ''),
  year: String(route.query.year || ''),
  ordering: String(route.query.ordering || '-updated_at'),
  limit: pageSize,
  offset: 0,
}, {
  urlKeys: ['q', 'status', 'source', 'genre', 'year', 'ordering'],
})
const filterDefaults: Partial<AdminSeriesFilters> = {
  q: '', status: '', source: '', genre: '', year: '',
  ordering: '-updated_at',
}

const hasActiveFilters = computed(() => Boolean(filters.q || filters.status || filters.source || filters.genre || filters.year))

const selectClass = 'admin-focus h-11 w-full min-w-0 rounded-xl border border-[var(--admin-border)] bg-white px-3 text-xs font-bold outline-none focus:border-[var(--admin-accent)]'

async function loadSeries() {
  loading.value = true
  error.value = null
  filters.offset = (page.value - 1) * pageSize
  try {
    const response: AdminSeriesListResponse = await adminApi.list(filters)
    seriesList.value = response.results
    total.value = response.count
  } catch (cause) {
    error.value = getAppError(cause, 'فهرست سریال‌ها دریافت نشد.')
  } finally {
    loading.value = false
  }
}

async function loadMeta() {
  try {
    genres.value = await adminApi.genres()
  } catch {
    genres.value = []
  }
}

debouncedWatch(() => {
  syncQuery()
  void loadSeries()
}, [() => filters.status, () => filters.source, () => filters.genre, () => filters.year, () => filters.ordering])

watch(page, () => {
  syncQuery()
  void loadSeries()
})

async function setPublished(item: AdminSeries, is_published: boolean) {
  actionLoading.value = true
  try {
    const saved = await adminApi.setPublished(item.id, is_published)
    seriesList.value = seriesList.value.map(row => row.id === item.id ? saved : row)
    notifications.success(is_published ? 'منتشر شد' : 'از انتشار خارج شد', item.title)
  } catch (cause) {
    notifications.notifyError(cause, 'تغییر وضعیت انتشار انجام نشد.')
  } finally {
    actionLoading.value = false
  }
}

async function archiveItem(item: AdminSeries) {
  actionLoading.value = true
  try {
    await adminApi.archive(item.id)
    seriesList.value = seriesList.value.map(row => row.id === item.id ? { ...row, is_published: false } : row)
    notifications.success('از سایت عمومی برداشته شد', item.title)
  } catch (cause) {
    notifications.notifyError(cause, 'آرشیو سریال انجام نشد.')
  } finally {
    actionLoading.value = false
  }
}

const syncTarget = ref<AdminSeries | null>(null)
const syncDryRun = ref<TMDBImportResponse | null>(null)
const syncOverwrite = ref(false)
const syncLoading = ref(false)

async function openSync(item: AdminSeries) {
  syncTarget.value = item
  syncDryRun.value = null
  syncOverwrite.value = false
  syncLoading.value = true
  try {
    syncDryRun.value = await adminApi.sync(item.id, { dry_run: true, overwrite_manual: false })
  } catch (cause) {
    notifications.notifyError(cause, 'پیش‌نمایش همگام‌سازی آماده نشد')
    syncTarget.value = null
  } finally {
    syncLoading.value = false
  }
}

async function confirmSync() {
  if (!syncTarget.value) return
  syncLoading.value = true
  try {
    await adminApi.sync(syncTarget.value.id, { overwrite_manual: syncOverwrite.value })
    notifications.success('همگام‌سازی کامل شد', 'اطلاعات TMDB با موفقیت به‌روزرسانی شد.')
    syncTarget.value = null
    await loadSeries()
  } catch (cause) {
    notifications.notifyError(cause, 'همگام‌سازی انجام نشد')
  } finally {
    syncLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadMeta(), loadSeries()])
})
</script>

<template>
  <div class="space-y-5 px-4 py-5 sm:px-6 sm:py-7 lg:px-8 lg:py-9">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-xs font-bold text-[var(--admin-muted)]">کاتالوگ</p>
        <h1 class="mt-1 flex items-center gap-2 text-2xl font-black">
          <Tv class="size-6 text-[var(--admin-primary)]" />
          مدیریت سریال‌ها
        </h1>
        <p class="mt-1 text-xs text-[var(--admin-muted)]">لینک دانلود، دوبله و زیرنویس سریال‌ها را با سایت عمومی همگام کنید.</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <AdminButton variant="secondary" :disabled="loading" @click="loadSeries">
          <template #icon><Refresh class="size-4" :class="loading && 'animate-spin'" /></template>
          نوسازی
        </AdminButton>
        <AdminButton to="/admin/series/new">
          <template #icon><Plus class="size-4" /></template>
          افزودن سریال
        </AdminButton>
      </div>
    </header>

    <AdminCard class="p-4">
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <div class="relative xl:col-span-2">
          <Search class="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-[var(--admin-muted)]" />
          <input v-model="filters.q" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white pr-10 pl-3 text-sm" placeholder="عنوان، IMDb یا TMDB…">
        </div>
        <select v-model="filters.status" :class="selectClass">
          <option value="">همه وضعیت‌ها</option>
          <option value="published">منتشرشده</option>
          <option value="draft">پیش‌نویس</option>
        </select>
        <select v-model="filters.source" :class="selectClass">
          <option value="">همه منابع</option>
          <option value="tmdb">TMDB</option>
          <option value="manual">دستی</option>
        </select>
        <select v-model="filters.genre" :class="selectClass">
          <option value="">همه ژانرها</option>
          <option v-for="genre in genres" :key="genre.id" :value="genre.slug">{{ genre.title }}</option>
        </select>
        <button
          v-if="hasActiveFilters"
          type="button"
          class="admin-focus inline-flex min-h-11 items-center self-end rounded-lg px-2 text-xs font-bold text-[var(--admin-accent)] hover:underline"
          @click="clearFilters(filterDefaults)"
        >
          پاک کردن فیلترها
        </button>
      </div>
    </AdminCard>

    <UiErrorAlert v-if="error" :error="error" @close="error = null" />

    <AdminCard class="overflow-hidden">
      <div v-if="loading" class="space-y-3 p-4">
        <div v-for="n in 6" :key="n" class="h-14 animate-pulse rounded-xl bg-[var(--admin-surface-muted)]" />
      </div>
      <AdminState
        v-else-if="!seriesList.length"
        kind="empty"
        :title="hasActiveFilters ? 'سریالی با این فیلتر پیدا نشد' : 'هنوز سریالی ثبت نشده است'"
        message="از TMDB یا فرم دستی سریال اضافه کنید."
      />
      <div v-else class="responsive-table">
        <table class="min-w-[760px] text-sm">
          <thead class="bg-[var(--admin-surface-muted)]/60 text-xs text-[var(--admin-muted)]">
            <tr>
              <th class="px-4 py-3 text-right font-bold">سریال</th>
              <th class="px-4 py-3 text-right font-bold">سال</th>
              <th class="px-4 py-3 text-right font-bold">نسخه</th>
              <th class="px-4 py-3 text-right font-bold">وضعیت</th>
              <th class="px-4 py-3 text-right font-bold">عملیات</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in seriesList" :key="item.id" class="border-t border-[var(--admin-border)]">
              <td class="px-4 py-3">
                <div class="flex items-center gap-3">
                  <img v-if="item.poster_url" :src="item.poster_url" alt="" class="h-14 w-10 rounded-lg object-cover">
                  <div class="min-w-0">
                    <NuxtLink :to="`/admin/series/${item.id}/edit`" class="block truncate font-black hover:text-[var(--admin-primary)]">{{ item.title }}</NuxtLink>
                    <p class="truncate text-xs text-[var(--admin-muted)]">{{ item.original_title || item.slug }}</p>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 tabular-nums">{{ item.start_year || '—' }}</td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  <span v-if="item.is_dubbed" class="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-black text-emerald-800">دوبله</span>
                  <span v-if="item.has_subtitle" class="rounded-md bg-sky-50 px-1.5 py-0.5 text-[10px] font-black text-sky-800">زیرنویس</span>
                  <span v-if="!item.is_dubbed && !item.has_subtitle" class="text-xs text-[var(--admin-muted)]">—</span>
                </div>
              </td>
              <td class="px-4 py-3">
                <span class="rounded-lg px-2 py-1 text-[10px] font-black" :class="item.is_published ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'">
                  {{ item.is_published ? 'منتشرشده' : 'پیش‌نویس' }}
                </span>
              </td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1.5">
                  <NuxtLink :to="`/admin/series/${item.id}/edit`" class="admin-focus inline-flex min-h-11 items-center rounded-lg bg-[var(--admin-surface-muted)] px-2.5 py-1.5 text-[11px] font-bold">ویرایش</NuxtLink>
                  <button
                    v-if="item.tmdb_id"
                    type="button"
                    class="admin-focus min-h-11 rounded-lg bg-teal-50 px-2.5 py-1.5 text-[11px] font-bold text-teal-800 disabled:opacity-40"
                    :disabled="actionLoading"
                    @click="openSync(item)"
                  >
                    همگام‌سازی
                  </button>
                  <button
                    type="button"
                    class="admin-focus min-h-11 rounded-lg px-2.5 py-1.5 text-[11px] font-bold disabled:opacity-40"
                    :class="item.is_published ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800'"
                    :disabled="actionLoading"
                    @click="setPublished(item, !item.is_published)"
                  >
                    {{ item.is_published ? 'لغو انتشار' : 'انتشار' }}
                  </button>
                  <button
                    type="button"
                    class="admin-focus min-h-11 rounded-lg bg-red-50 px-2.5 py-1.5 text-[11px] font-bold text-[var(--admin-danger)] disabled:opacity-40"
                    :disabled="actionLoading || !item.is_published"
                    @click="archiveItem(item)"
                  >
                    حذف از سایت
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <AdminPagination
        :page="page"
        :total="total"
        :page-size="pageSize"
        :loading="loading"
        @update:page="page = $event"
      />
    </AdminCard>

    <AdminModal
      :open="Boolean(syncTarget)"
      title="همگام‌سازی با TMDB"
      :description="`اطلاعات «${syncTarget?.title || ''}» ابتدا به‌صورت dry-run بررسی شده است.`"
      size="sm"
      :closeable="!syncLoading"
      @close="syncTarget = null"
    >
      <div class="p-6">
        <div v-if="syncLoading && !syncDryRun" class="py-8 text-center text-sm text-[var(--admin-muted)]">در حال بررسی تغییرات…</div>
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
          <AdminButton variant="ghost" :disabled="syncLoading" @click="syncTarget = null">انصراف</AdminButton>
          <AdminButton :loading="syncLoading" @click="confirmSync">همگام‌سازی</AdminButton>
        </div>
      </template>
    </AdminModal>
  </div>
</template>

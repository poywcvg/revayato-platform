<script setup lang="ts">
import type { AdminSeries, AdminSeriesListResponse } from '~/types/admin'
import Tv from '~icons/lucide/tv'
import Search from '~icons/lucide/search'
import Star from '~icons/lucide/star'
import Eye from '~icons/lucide/eye'
import EyeOff from '~icons/lucide/eye-off'
import Archive from '~icons/lucide/archive'
import ExternalLink from '~icons/lucide/external-link'
import Pencil from '~icons/lucide/pencil'
import ChevronRight from '~icons/lucide/chevron-right'
import ChevronLeft from '~icons/lucide/chevron-left'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'مدیریت سریال‌ها — روایتو' })

const { api } = useApi()
const notify = useNotifications()

const PAGE_SIZE = 20
const q = ref('')
const qDebounced = ref('')
const statusFilter = ref<'' | 'published' | 'draft'>('')
const offset = ref(0)

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(q, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { qDebounced.value = val.trim(); offset.value = 0 }, 350)
})
watch(statusFilter, () => { offset.value = 0 })

const STATUS_OPTIONS: { value: '' | 'published' | 'draft', label: string }[] = [
  { value: '', label: 'همه وضعیت‌ها' },
  { value: 'published', label: 'منتشر شده' },
  { value: 'draft', label: 'پیش‌نویس' },
]

const { data, pending, error, refresh } = await useAsyncData(
  'admin-series',
  () => api<AdminSeriesListResponse>('/admin/series/', {
    query: {
      q: qDebounced.value || undefined,
      status: statusFilter.value || undefined,
      limit: PAGE_SIZE,
      offset: offset.value,
    },
  }),
  { watch: [qDebounced, statusFilter, offset] },
)

const rows = computed(() => data.value?.results ?? [])
const total = computed(() => data.value?.count ?? 0)
const from = computed(() => (total.value === 0 ? 0 : offset.value + 1))
const to = computed(() => Math.min(offset.value + PAGE_SIZE, total.value))

const busy = ref<Record<number, boolean>>({})
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

// ----- Bulk selection ----------------------------------------------------- //
// Scoped to the visible page — see the note on the films list.
const selected = ref<number[]>([])
watch([qDebounced, statusFilter, offset], () => { selected.value = [] })

const allSelected = computed(() => rows.value.length > 0 && selected.value.length === rows.value.length)
function toggleAll() {
  selected.value = allSelected.value ? [] : rows.value.map(series => series.id)
}
function toggleOne(id: number) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter(value => value !== id)
    : [...selected.value, id]
}
async function afterBulk() {
  await refresh()
  selected.value = []
}

const SERIES_STATUS_LABEL: Record<string, string> = {
  ongoing: 'در حال پخش',
  ended: 'پایان‌یافته',
  upcoming: 'به‌زودی',
  cancelled: 'لغو شده',
  on_hold: 'متوقف',
}

async function patchSeries(series: AdminSeries, payload: Record<string, unknown>, okMsg: string) {
  busy.value = { ...busy.value, [series.id]: true }
  try {
    await api(`/admin/series/${series.id}/`, { method: 'PATCH', body: payload })
    notify.success('انجام شد', okMsg)
    await refresh()
  }
  catch { notify.error('خطا', 'عملیات ناموفق بود') }
  finally { busy.value = { ...busy.value, [series.id]: false } }
}

function togglePublish(series: AdminSeries) {
  patchSeries(series, { is_published: !series.is_published }, series.is_published ? 'به پیش‌نویس منتقل شد' : 'منتشر شد')
}
function toggleFeatured(series: AdminSeries) {
  patchSeries(series, { is_featured: !series.is_featured }, series.is_featured ? 'از ویژه‌ها حذف شد' : 'به ویژه‌ها افزوده شد')
}
async function archiveSeries(series: AdminSeries) {
  if (!window.confirm(`«${series.title}» بایگانی شود؟`)) return
  busy.value = { ...busy.value, [series.id]: true }
  try {
    await api(`/admin/series/${series.id}/`, { method: 'DELETE' })
    notify.success('انجام شد', 'بایگانی شد')
    await refresh()
  }
  catch { notify.error('خطا', 'عملیات ناموفق بود') }
  finally { busy.value = { ...busy.value, [series.id]: false } }
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">سریال‌ها</h1>
      <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">{{ fa(total) }} عنوان در کتابخانه</p>
    </div>

    <div class="flex flex-wrap items-center gap-3">
      <div class="relative min-w-[200px] flex-1">
        <Search class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--rv-faint)]" />
        <input v-model="q" type="search" placeholder="جستجوی عنوان، IMDb یا TMDb…" class="rv-input !pr-9">
      </div>
      <select v-model="statusFilter" class="rv-input !w-auto">
        <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
    </div>

    <RvPanel :icon="Tv" :padded="false">
      <template #actions>
        <span v-if="total" class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
      </template>

      <RvState v-if="error" kind="error" title="خطا در دریافت فهرست" @retry="refresh()" />
      <RvState v-else-if="!pending && rows.length === 0" title="سریالی یافت نشد" message="با فیلترهای دیگری امتحان کنید." />

      <div v-else class="overflow-x-auto">
        <table class="rv-table">
          <thead>
            <tr>
              <th class="w-10">
                <input
                  type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]"
                  :checked="allSelected" aria-label="انتخاب همهٔ ردیف‌های این صفحه" @change="toggleAll"
                >
              </th>
              <th>عنوان</th>
              <th>سال</th>
              <th>وضعیت پخش</th>
              <th>انتشار</th>
              <th class="text-center">اقدامات</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="pending && rows.length === 0">
              <tr v-for="i in 8" :key="`sk${i}`">
                <td colspan="6"><div class="rv-skeleton h-9 w-full" /></td>
              </tr>
            </template>
            <tr v-for="series in rows" :key="series.id">
              <td>
                <input
                  type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]"
                  :checked="selected.includes(series.id)" :aria-label="`انتخاب ${series.title}`"
                  @change="toggleOne(series.id)"
                >
              </td>
              <td>
                <div class="flex items-center gap-3">
                  <div class="h-14 w-10 shrink-0 overflow-hidden rounded-md bg-[var(--rv-surface-3)]">
                    <img v-if="series.poster_url" :src="series.poster_url" :alt="series.title" class="size-full object-cover" loading="lazy">
                  </div>
                  <div class="min-w-0">
                    <NuxtLink :to="`/admin/series/${series.id}`" class="rv-focus block truncate font-bold text-[var(--rv-text)] hover:text-[var(--rv-accent)]">
                      {{ series.title }}
                    </NuxtLink>
                    <p v-if="series.original_title && series.original_title !== series.title" class="truncate text-xs text-[var(--rv-faint)]" dir="ltr">{{ series.original_title }}</p>
                  </div>
                </div>
              </td>
              <td class="tabular-nums text-[var(--rv-muted)]">{{ series.start_year ? fa(series.start_year) : '—' }}</td>
              <td><RvBadge tone="info">{{ SERIES_STATUS_LABEL[series.status] ?? series.status }}</RvBadge></td>
              <td><RvBadge :tone="series.is_published ? 'success' : 'warning'" dot>{{ series.is_published ? 'منتشر شده' : 'پیش‌نویس' }}</RvBadge></td>
              <td>
                <div class="flex items-center justify-center gap-1">
                  <button
                    type="button" class="rv-icon-btn rv-focus" :disabled="busy[series.id]"
                    :title="series.is_featured ? 'حذف از ویژه‌ها' : 'افزودن به ویژه‌ها'"
                    :style="series.is_featured ? { color: 'var(--rv-warning)' } : {}"
                    @click="toggleFeatured(series)"
                  >
                    <Star class="size-4" :fill="series.is_featured ? 'currentColor' : 'none'" />
                  </button>
                  <button
                    type="button" class="rv-icon-btn rv-focus" :disabled="busy[series.id]"
                    :title="series.is_published ? 'به پیش‌نویس' : 'انتشار'"
                    @click="togglePublish(series)"
                  >
                    <component :is="series.is_published ? EyeOff : Eye" class="size-4" />
                  </button>
                  <NuxtLink :to="`/admin/series/${series.id}`" class="rv-icon-btn rv-focus" title="ویرایش">
                    <Pencil class="size-4" />
                  </NuxtLink>
                  <NuxtLink :to="`/series/${series.slug}`" target="_blank" class="rv-icon-btn rv-focus" title="مشاهده در سایت">
                    <ExternalLink class="size-4" />
                  </NuxtLink>
                  <button
                    v-if="series.is_published"
                    type="button" class="rv-icon-btn rv-icon-btn--danger rv-focus" :disabled="busy[series.id]"
                    title="بایگانی" @click="archiveSeries(series)"
                  >
                    <Archive class="size-4" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="total > PAGE_SIZE" class="flex items-center justify-between gap-3 border-t border-[var(--rv-border)] px-4 py-3">
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="offset === 0 || pending" @click="offset = Math.max(0, offset - PAGE_SIZE)">
          <ChevronRight class="size-4" /> قبلی
        </button>
        <span class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="to >= total || pending" @click="offset = offset + PAGE_SIZE">
          بعدی <ChevronLeft class="size-4" />
        </button>
      </div>
    </RvPanel>

    <RvBulkBar kind="series" :ids="selected" @done="afterBulk" @clear="selected = []" />
  </div>
</template>

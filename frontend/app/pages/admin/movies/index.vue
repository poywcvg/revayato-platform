<script setup lang="ts">
import type {
  AdminMovie,
  AdminMovieListResponse,
  MoviePublicationStatus,
} from '~/types/admin'
import Film from '~icons/lucide/film'
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
useSeoMeta({ title: 'مدیریت فیلم‌ها — روایتو' })

const { api } = useApi()
const notify = useNotifications()

const PAGE_SIZE = 20
const q = ref('')
const qDebounced = ref('')
const statusFilter = ref<'' | MoviePublicationStatus>('')
const typeFilter = ref('')
const offset = ref(0)

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(q, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { qDebounced.value = val.trim(); offset.value = 0 }, 350)
})
watch([statusFilter, typeFilter], () => { offset.value = 0 })

const STATUS_OPTIONS: { value: '' | MoviePublicationStatus, label: string }[] = [
  { value: '', label: 'همه وضعیت‌ها' },
  { value: 'published', label: 'منتشر شده' },
  { value: 'draft', label: 'پیش‌نویس' },
  { value: 'archived', label: 'بایگانی' },
]
const TYPE_OPTIONS = [
  { value: '', label: 'همه انواع' },
  { value: 'movie', label: 'فیلم' },
  { value: 'documentary', label: 'مستند' },
  { value: 'short', label: 'کوتاه' },
]

const { data, pending, error, refresh } = await useAsyncData(
  'admin-movies',
  () => api<AdminMovieListResponse>('/admin/movies/', {
    query: {
      q: qDebounced.value || undefined,
      status: statusFilter.value || undefined,
      type: typeFilter.value || undefined,
      limit: PAGE_SIZE,
      offset: offset.value,
    },
  }),
  { watch: [qDebounced, statusFilter, typeFilter, offset] },
)

const rows = computed(() => data.value?.results ?? [])
const total = computed(() => data.value?.count ?? 0)
const from = computed(() => (total.value === 0 ? 0 : offset.value + 1))
const to = computed(() => Math.min(offset.value + PAGE_SIZE, total.value))

const busy = ref<Record<number, boolean>>({})
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

// ----- Bulk selection ----------------------------------------------------- //
// Scoped to the visible page on purpose: a "select all 4,000" that quietly
// archives titles the admin never looked at is exactly the mistake the audit
// trail exists to explain, and it is cheaper not to offer it.
const selected = ref<number[]>([])
watch([qDebounced, statusFilter, typeFilter, offset], () => { selected.value = [] })

const allSelected = computed(() => rows.value.length > 0 && selected.value.length === rows.value.length)
function toggleAll() {
  selected.value = allSelected.value ? [] : rows.value.map(movie => movie.id)
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

const STATUS_TONE: Record<MoviePublicationStatus, 'success' | 'warning' | 'neutral'> = {
  published: 'success',
  draft: 'warning',
  archived: 'neutral',
}
const STATUS_LABEL: Record<MoviePublicationStatus, string> = {
  published: 'منتشر شده',
  draft: 'پیش‌نویس',
  archived: 'بایگانی',
}
const TYPE_LABEL: Record<string, string> = { movie: 'فیلم', documentary: 'مستند', short: 'کوتاه' }

async function patchMovie(movie: AdminMovie, payload: Record<string, unknown>, okMsg: string) {
  busy.value = { ...busy.value, [movie.id]: true }
  try {
    await api(`/admin/movies/${movie.id}/`, { method: 'PATCH', body: payload })
    notify.success('انجام شد', okMsg)
    await refresh()
  }
  catch (err) {
    notify.error('انجام نشد', adminErrorMessage(err))
  }
  finally {
    busy.value = { ...busy.value, [movie.id]: false }
  }
}

function togglePublish(movie: AdminMovie) {
  const next: MoviePublicationStatus = movie.publication_status === 'published' ? 'draft' : 'published'
  patchMovie(movie, { publication_status: next }, next === 'published' ? 'منتشر شد' : 'به پیش‌نویس منتقل شد')
}
function toggleFeatured(movie: AdminMovie) {
  patchMovie(movie, { is_featured: !movie.is_featured }, movie.is_featured ? 'از ویژه‌ها حذف شد' : 'به ویژه‌ها افزوده شد')
}
async function archiveMovie(movie: AdminMovie) {
  if (!window.confirm(`«${movie.title}» بایگانی شود؟`)) return
  busy.value = { ...busy.value, [movie.id]: true }
  try {
    await api(`/admin/movies/${movie.id}/`, { method: 'DELETE' })
    notify.success('انجام شد', 'بایگانی شد')
    await refresh()
  }
  catch (err) { notify.error('انجام نشد', adminErrorMessage(err)) }
  finally { busy.value = { ...busy.value, [movie.id]: false } }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">فیلم‌ها</h1>
        <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">{{ fa(total) }} عنوان در کتابخانه</p>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-center gap-3">
      <div class="relative min-w-[200px] flex-1">
        <Search class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--rv-faint)]" />
        <input v-model="q" type="search" placeholder="جستجوی عنوان، IMDb یا TMDb…" class="rv-input !pr-9">
      </div>
      <select v-model="statusFilter" class="rv-input !w-auto">
        <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <select v-model="typeFilter" class="rv-input !w-auto">
        <option v-for="o in TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
    </div>

    <RvPanel :icon="Film" :padded="false">
      <template #actions>
        <span v-if="total" class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
      </template>

      <RvState v-if="error" kind="error" title="خطا در دریافت فهرست" @retry="refresh()" />
      <RvState v-else-if="!pending && rows.length === 0" title="فیلمی یافت نشد" message="با فیلترهای دیگری امتحان کنید." />

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
              <th>نوع</th>
              <th>وضعیت</th>
              <th class="text-center">اقدامات</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="pending && rows.length === 0">
              <tr v-for="i in 8" :key="`sk${i}`">
                <td colspan="6"><div class="rv-skeleton h-9 w-full" /></td>
              </tr>
            </template>
            <tr v-for="movie in rows" :key="movie.id">
              <td>
                <input
                  type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]"
                  :checked="selected.includes(movie.id)" :aria-label="`انتخاب ${movie.title}`"
                  @change="toggleOne(movie.id)"
                >
              </td>
              <td>
                <div class="flex items-center gap-3">
                  <div class="h-14 w-10 shrink-0 overflow-hidden rounded-md bg-[var(--rv-surface-3)]">
                    <img v-if="movie.poster_url" :src="movie.poster_url" :alt="movie.title" class="size-full object-cover" loading="lazy">
                  </div>
                  <div class="min-w-0">
                    <NuxtLink :to="`/admin/movies/${movie.id}`" class="rv-focus block truncate font-bold text-[var(--rv-text)] hover:text-[var(--rv-accent)]">
                      {{ movie.title }}
                    </NuxtLink>
                    <p v-if="movie.original_title && movie.original_title !== movie.title" class="truncate text-xs text-[var(--rv-faint)]" dir="ltr">{{ movie.original_title }}</p>
                  </div>
                </div>
              </td>
              <td class="tabular-nums text-[var(--rv-muted)]">{{ movie.release_year ? fa(movie.release_year) : '—' }}</td>
              <td><RvBadge tone="info">{{ TYPE_LABEL[movie.catalog_type] ?? movie.catalog_type }}</RvBadge></td>
              <td><RvBadge :tone="STATUS_TONE[movie.publication_status]" dot>{{ STATUS_LABEL[movie.publication_status] }}</RvBadge></td>
              <td>
                <div class="flex items-center justify-center gap-1">
                  <button
                    type="button" class="rv-icon-btn rv-focus" :disabled="busy[movie.id]"
                    :title="movie.is_featured ? 'حذف از ویژه‌ها' : 'افزودن به ویژه‌ها'"
                    :style="movie.is_featured ? { color: 'var(--rv-warning)' } : {}"
                    @click="toggleFeatured(movie)"
                  >
                    <Star class="size-4" :fill="movie.is_featured ? 'currentColor' : 'none'" />
                  </button>
                  <button
                    type="button" class="rv-icon-btn rv-focus" :disabled="busy[movie.id]"
                    :title="movie.publication_status === 'published' ? 'به پیش‌نویس' : 'انتشار'"
                    @click="togglePublish(movie)"
                  >
                    <component :is="movie.publication_status === 'published' ? EyeOff : Eye" class="size-4" />
                  </button>
                  <NuxtLink :to="`/admin/movies/${movie.id}`" class="rv-icon-btn rv-focus" title="ویرایش">
                    <Pencil class="size-4" />
                  </NuxtLink>
                  <NuxtLink :to="`/movies/${movie.slug}`" target="_blank" class="rv-icon-btn rv-focus" title="مشاهده در سایت">
                    <ExternalLink class="size-4" />
                  </NuxtLink>
                  <button
                    v-if="movie.publication_status !== 'archived'"
                    type="button" class="rv-icon-btn rv-icon-btn--danger rv-focus" :disabled="busy[movie.id]"
                    title="بایگانی" @click="archiveMovie(movie)"
                  >
                    <Archive class="size-4" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
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

    <RvBulkBar kind="movie" :ids="selected" @done="afterBulk" @clear="selected = []" />
  </div>
</template>

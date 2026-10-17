<script setup lang="ts">
import type {
  AdminMovieListResponse,
  AdminSeriesListResponse,
  AdminSliderItem,
  AdminSliderListResponse,
  AdminSliderReorderItem,
  SliderContentType,
  SliderPlatform,
} from '~/types/admin'
import GalleryHorizontal from '~icons/lucide/gallery-horizontal'
import Search from '~icons/lucide/search'
import Plus from '~icons/lucide/plus'
import Trash from '~icons/lucide/trash-2'
import ChevronUp from '~icons/lucide/chevron-up'
import ChevronDown from '~icons/lucide/chevron-down'
import ArrowUpDown from '~icons/lucide/arrow-up-down'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'اسلایدر خانه — روایتو' })

const { api } = useApi()
const notify = useNotifications()

const PLATFORM_OPTIONS: { value: '' | SliderPlatform, label: string }[] = [
  { value: '', label: 'همه پلتفرم‌ها' },
  { value: 'all', label: 'وب‌سایت و اپلیکیشن' },
  { value: 'web', label: 'فقط وب‌سایت' },
  { value: 'app', label: 'فقط اپلیکیشن' },
]
const PLATFORM_LABEL: Record<SliderPlatform, string> = {
  all: 'وب و اپ',
  web: 'وب',
  app: 'اپ',
}
const TYPE_LABEL: Record<SliderContentType, string> = { movie: 'فیلم', series: 'سریال' }

const platformFilter = ref<'' | SliderPlatform>('')
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

const { data, pending, error, refresh } = await useAsyncData(
  'admin-slider',
  () => api<AdminSliderListResponse>('/admin/slider/', {
    query: { platform: platformFilter.value || undefined, limit: 60 },
  }),
  { watch: [platformFilter] },
)

// ----- Local editable copy ------------------------------------------------ //
// Reordering / platform / membership are staged locally and saved with one
// POST /admin/slider/reorder/ so the slider never sits half-saved.
const rows = ref<AdminSliderItem[]>([])
const removed = ref<AdminSliderReorderItem[]>([])
const dirty = ref(false)
watch(data, (val) => {
  rows.value = (val?.results ?? []).map(item => ({ ...item }))
  removed.value = []
  dirty.value = false
  unpublishedWarning.value = []
}, { immediate: true })

const saving = ref(false)
const unpublishedWarning = ref<Array<{ content_type: string, id: number, title: string }>>([])

function move(index: number, delta: -1 | 1) {
  const target = index + delta
  if (target < 0 || target >= rows.value.length) return
  const list = [...rows.value]
  const [item] = list.splice(index, 1)
  if (!item) return
  list.splice(target, 0, item)
  list.forEach((row, i) => { row.featured_order = i + 1; row.slider_order = i + 1 })
  rows.value = list
  dirty.value = true
}

function removeRow(index: number) {
  const [item] = rows.value.splice(index, 1)
  if (item) {
    removed.value.push({ content_type: item.content_type, id: item.id, is_featured: false })
    rows.value.forEach((row, i) => { row.featured_order = i + 1; row.slider_order = i + 1 })
    dirty.value = true
  }
}

function touch() {
  dirty.value = true
}

async function save() {
  saving.value = true
  try {
    const items: AdminSliderReorderItem[] = [
      ...rows.value.map((row, i) => ({
        content_type: row.content_type,
        id: row.id,
        is_featured: true,
        featured_order: i + 1,
        slider_platform: row.slider_platform,
      })),
      ...removed.value,
    ]
    const saved = await api<{ unpublished?: Array<{ content_type: string, id: number, title: string }> }>('/admin/slider/reorder/', { method: 'POST', body: { items } })
    unpublishedWarning.value = saved?.unpublished ?? []
    if (unpublishedWarning.value.length) {
      notify.error(
        'چند عنوان منتشر نشده‌اند',
        `${fa(unpublishedWarning.value.length)} عنوان ویژه است ولی چون منتشر نشده در اسلایدر نمایش داده نمی‌شود.`,
      )
    }
    else {
      notify.success('انجام شد', 'اسلایدر خانه ذخیره شد')
    }
    await refresh()
  }
  catch (err) {
    notify.error('انجام نشد', adminErrorMessage(err))
  }
  finally {
    saving.value = false
  }
}

// ----- Add titles --------------------------------------------------------- //
const addTab = ref<SliderContentType>('movie')
const addQuery = ref('')
const addQueryDebounced = ref('')
let addTimer: ReturnType<typeof setTimeout> | null = null
watch(addQuery, (val) => {
  if (addTimer) clearTimeout(addTimer)
  addTimer = setTimeout(() => { addQueryDebounced.value = val.trim() }, 350)
})

const { data: addData, pending: addPending } = await useAsyncData<
  AdminMovieListResponse | AdminSeriesListResponse
>(
  'admin-slider-add',
  () => {
    if (addTab.value === 'movie') {
      return api<AdminMovieListResponse>('/admin/movies/', {
        query: { q: addQueryDebounced.value || undefined, status: 'published', limit: 8, offset: 0 },
      })
    }
    return api<AdminSeriesListResponse>('/admin/series/', {
      query: { q: addQueryDebounced.value || undefined, status: 'published', limit: 8, offset: 0 },
    })
  },
  { watch: [addTab, addQueryDebounced] },
)

const addResults = computed(() => {
  const list = (addData.value?.results ?? []) as Array<{
    id: number; title: string; original_title?: string; slug: string;
    poster_url?: string | null; backdrop_url?: string | null;
    release_year?: number | null; start_year?: number | null;
    is_featured?: boolean; featured_order?: number; slider_platform?: SliderPlatform;
  }>
  const present = new Set(rows.value.map(row => `${row.content_type}:${row.id}`))
  return list
    .filter(item => !present.has(`${addTab.value}:${item.id}`))
    .slice(0, 8)
})

type AddCandidate = {
  id: number; title: string; original_title?: string; slug: string;
  poster_url?: string | null; backdrop_url?: string | null;
  release_year?: number | null; start_year?: number | null;
}

function addTitle(item: AddCandidate) {
  const order = rows.value.length + 1
  rows.value.push({
    id: item.id,
    content_type: addTab.value,
    title: item.title,
    original_title: item.original_title,
    slug: item.slug,
    poster_url: item.poster_url ?? null,
    backdrop_url: item.backdrop_url ?? null,
    release_year: item.release_year ?? null,
    start_year: item.start_year ?? null,
    is_published: true,
    is_featured: true,
    featured_order: order,
    slider_order: order,
    slider_platform: 'all',
    updated_at: new Date().toISOString(),
  })
  dirty.value = true
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">اسلایدر خانه</h1>
        <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">
          انتخاب عنوان‌های اسلایدر اصلی وب‌سایت و اپلیکیشن — کمتر یعنی اول‌تر.
          بعد از «ذخیره ترتیب»، سرور بلافاصله تازه می‌شود و وب و اپ حداکثر تا یک دقیقه بعد همه‌جا یکسان می‌شوند.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <select v-model="platformFilter" class="rv-input !w-auto">
          <option value="">نمایش: همه</option>
          <option value="all">وب و اپ</option>
          <option value="web">فقط وب</option>
          <option value="app">فقط اپ</option>
        </select>
        <button
          type="button" class="rv-btn rv-focus" :disabled="!dirty || saving"
          @click="save"
        >
          <ArrowUpDown class="size-4" /> {{ saving ? 'در حال ذخیره…' : 'ذخیره ترتیب' }}
        </button>
      </div>
    </div>

    <RvPanel :icon="GalleryHorizontal" :padded="false">
      <RvState v-if="error" kind="error" title="خطا در دریافت اسلایدر" @retry="refresh()" />
      <div v-else-if="unpublishedWarning.length" class="border-b border-[var(--rv-border)] bg-amber-500/10 px-4 py-3 text-xs font-bold text-[var(--rv-text)]">
        این عنوان‌ها ویژه‌اند ولی چون منتشر نشده‌اند در اسلایدر دیده نمی‌شوند — منتشرشان کنید تا در وب‌سایت و اپلیکیشن بیایند:
        <span class="text-[var(--rv-muted)]">{{ unpublishedWarning.map(w => w.title).join('، ') }}</span>
      </div>
      <RvState v-else-if="!pending && rows.length === 0" title="اسلایدر خالی است" message="از بخش افزودن، فیلم و سریال به اسلایدر اضافه کنید." />
      <div v-else class="overflow-x-auto">
        <table class="rv-table">
          <thead>
            <tr>
              <th class="w-14">ترتیب</th>
              <th>عنوان</th>
              <th>نوع</th>
              <th>پلتفرم</th>
              <th>وضعیت</th>
              <th class="text-center">اقدامات</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="pending && rows.length === 0">
              <tr v-for="i in 6" :key="`sk${i}`">
                <td colspan="6"><div class="rv-skeleton h-12 w-full" /></td>
              </tr>
            </template>
            <tr v-for="(row, index) in rows" :key="`${row.content_type}:${row.id}`">
              <td>
                <input
                  v-model.number="row.featured_order" type="number" min="1" max="9999"
                  class="rv-input !w-16 !px-2 text-center tabular-nums" @change="touch"
                >
              </td>
              <td>
                <div class="flex items-center gap-3">
                  <div class="h-14 w-10 shrink-0 overflow-hidden rounded-md bg-[var(--rv-surface-3)]">
                    <img v-if="row.poster_url" :src="row.poster_url" :alt="row.title" class="size-full object-cover" loading="lazy">
                  </div>
                  <div class="min-w-0">
                    <span class="block truncate font-bold text-[var(--rv-text)]">{{ fa(index + 1) }}. {{ row.title }}</span>
                    <p v-if="row.original_title && row.original_title !== row.title" class="truncate text-xs text-[var(--rv-faint)]" dir="ltr">{{ row.original_title }}</p>
                  </div>
                </div>
              </td>
              <td><RvBadge tone="info">{{ TYPE_LABEL[row.content_type] }}</RvBadge></td>
              <td>
                <select v-model="row.slider_platform" class="rv-input !w-auto !min-h-9 !py-1 text-xs" @change="touch">
                  <option v-for="o in PLATFORM_OPTIONS.slice(1)" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
              </td>
              <td>
                <RvBadge :tone="row.is_published ? 'success' : 'warning'" dot>
                  {{ row.is_published ? (PLATFORM_LABEL[row.slider_platform] ?? '') : 'پیش‌نویس' }}
                </RvBadge>
              </td>
              <td>
                <div class="flex items-center justify-center gap-1">
                  <button type="button" class="rv-icon-btn rv-focus" title="بالا" :disabled="index === 0" @click="move(index, -1)">
                    <ChevronUp class="size-4" />
                  </button>
                  <button type="button" class="rv-icon-btn rv-focus" title="پایین" :disabled="index === rows.length - 1" @click="move(index, 1)">
                    <ChevronDown class="size-4" />
                  </button>
                  <button type="button" class="rv-icon-btn rv-icon-btn--danger rv-focus" title="حذف از اسلایدر" @click="removeRow(index)">
                    <Trash class="size-4" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </RvPanel>

    <RvPanel title="افزودن به اسلایدر" :icon="Plus">
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex overflow-hidden rounded-lg border border-[var(--rv-border)]">
          <button
            type="button" class="rv-focus px-4 py-2 text-xs font-bold"
            :class="addTab === 'movie' ? 'bg-[var(--rv-accent)] text-white' : 'text-[var(--rv-muted)]'"
            @click="addTab = 'movie'"
          >فیلم</button>
          <button
            type="button" class="rv-focus px-4 py-2 text-xs font-bold"
            :class="addTab === 'series' ? 'bg-[var(--rv-accent)] text-white' : 'text-[var(--rv-muted)]'"
            @click="addTab = 'series'"
          >سریال</button>
        </div>
        <div class="relative min-w-[200px] flex-1">
          <Search class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--rv-faint)]" />
          <input v-model="addQuery" type="search" placeholder="جستجوی عنوان منتشرشده…" class="rv-input !pr-9">
        </div>
      </div>
      <div v-if="addPending" class="mt-4 space-y-2">
        <div v-for="i in 3" :key="`ask${i}`" class="rv-skeleton h-12 w-full" />
      </div>
      <div v-else-if="addResults.length === 0" class="mt-4">
        <RvState title="نتیجه‌ای نیست" message="عنوان دیگری را جستجو کنید — فقط عنوان‌های منتشرشده قابل افزودن‌اند." />
      </div>
      <ul v-else class="mt-4 space-y-2">
        <li
          v-for="item in addResults" :key="`${addTab}:${item.id}`"
          class="flex items-center justify-between gap-3 rounded-xl border border-[var(--rv-border)] px-3 py-2"
        >
          <div class="flex min-w-0 items-center gap-3">
            <div class="h-12 w-9 shrink-0 overflow-hidden rounded-md bg-[var(--rv-surface-3)]">
              <img v-if="item.poster_url" :src="item.poster_url" :alt="item.title" class="size-full object-cover" loading="lazy">
            </div>
            <div class="min-w-0">
              <p class="truncate text-sm font-bold text-[var(--rv-text)]">{{ item.title }}</p>
              <p class="text-xs text-[var(--rv-faint)]">
                {{ TYPE_LABEL[addTab] }}
                <template v-if="item.is_featured"> · در اسلایدر</template>
              </p>
            </div>
          </div>
          <button
            type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9"
            @click="addTitle(item)"
          >
            <Plus class="size-4" /> افزودن
          </button>
        </li>
      </ul>
      <p class="mt-3 text-xs text-[var(--rv-faint)]">افزودن‌ها پیش‌نویس می‌مانند تا «ذخیره ترتیب» را بزنید.</p>
    </RvPanel>
  </div>
</template>

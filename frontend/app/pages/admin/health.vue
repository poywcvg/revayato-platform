<script setup lang="ts">
/**
 * سلامت محتوا — every title the platform already knows is broken.
 *
 * None of this data is new. `PlaybackSourceGap`, `PlaybackSubtitleGap`,
 * `MediaCheck`, `ContentIssueReport` and `completeness.publish_blockers` have
 * been recording problems for as long as they have existed; the panel simply
 * never showed them, so the only way to learn a film would not play was for a
 * viewer to report it. Six queues, one per way a title can be broken:
 *
 *  · کمبود منبع — no browser-playable source (the MKV/HEVC-only case)
 *  · کمبود زیرنویس — subtitle extraction never produced a track
 *  · تست ناموفق — the probe reached the hosts and they said the files are gone
 *  · گزارش کاربران — a viewer pressed «گزارش خطا» and nothing has closed it
 *  · تأیید نشده — published, but nobody has verified it inside the freshness window
 *  · ناقص — published with a blocker the importer would have refused
 *
 * The last two are the uncomfortable ones: they are titles the site is currently
 * serving while failing its own standard, which is precisely why they belong on
 * the same page as the reported failures rather than in a report nobody opens.
 *
 * Any row can be sent to «بازسازی از صفر با تست»: the title is rebuilt from
 * every provider on a shadow copy, the new links are probed, and only a set
 * that passes replaces the old one (backed up, undoable from the title desk).
 * The «آخرین بازسازی» column shows what happened — replaced, or untouched and
 * why — and the list refreshes itself while any run is still going.
 * Either rebuild also repairs the problem that put the row here (playback,
 * subtitles, checks, reports, missing fields, score), and the column says which
 * were fixed, queued, or are still open.
 */
import type { AdminContentKind, HealthCounts, HealthQueue, HealthRow } from '~/types/admin'
import HeartPulse from '~icons/lucide/heart-pulse'
import Loader from '~icons/lucide/loader-circle'
import RefreshCw from '~icons/lucide/refresh-cw'
import ExternalLink from '~icons/lucide/external-link'
import Radar from '~icons/lucide/radar'
import ShieldCheck from '~icons/lucide/shield-check'
import Rebuild from '~icons/lucide/rotate-ccw'
import { anyRepairActive, repairBadge } from '~/utils/stagedRebuild'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'سلامت محتوا — روایتو' })

const { health, bulk } = useAdminOps()
const notify = useNotifications()

const PAGE_SIZE = 50

const QUEUES: { key: HealthQueue, label: string, hint: string }[] = [
  { key: 'source_gaps', label: 'کمبود منبع', hint: 'هیچ منبع سازگار با مرورگر ندارد' },
  { key: 'subtitle_gaps', label: 'کمبود زیرنویس', hint: 'استخراج زیرنویس نتیجه نداد' },
  { key: 'failed_checks', label: 'تست ناموفق', hint: 'میزبان‌ها گفته‌اند فایل‌ها رفته‌اند' },
  { key: 'reports', label: 'گزارش کاربران', hint: 'گزارش‌های باز کاربران' },
  { key: 'unverified', label: 'تأیید نشده', hint: 'منتشر شده ولی تست تازه‌ای ندارد' },
  { key: 'incomplete', label: 'ناقص', hint: 'منتشر شده با اطلاعات ناقص' },
  { key: 'approx_ratings', label: 'نمرهٔ تقریبی', hint: 'نمرهٔ IMDb واقعی نیست و جایگزین می‌شود' },
  { key: 'sourceless_drafts', label: 'بدون منبع', hint: 'عنوان منتشرنشده بدون هیچ لینک دانلودی؛ خزنده دنبال منبع می‌گردد' },
]

// The queue lives in the URL so the dashboard counters, a support thread and a
// bookmark can all point at one specific problem list rather than at "the health
// page, now go find the tab".
const route = useRoute()
const router = useRouter()
const QUEUE_KEYS = QUEUES.map(item => item.key)
const initial = String(route.query.queue || '')
const queue = ref<HealthQueue>(
  QUEUE_KEYS.includes(initial as HealthQueue) ? initial as HealthQueue : 'source_gaps',
)
const offset = ref(0)
watch(queue, (value) => {
  offset.value = 0
  void router.replace({ query: { ...route.query, queue: value } })
})
// A selection belongs to the page it was made on.
const selected = ref<string[]>([])
watch([queue, offset], () => { selected.value = [] })

const { data, pending, error, refresh } = await useAsyncData(
  'admin-health',
  () => health(queue.value, { limit: PAGE_SIZE, offset: offset.value }),
  { watch: [queue, offset] },
)

const counts = computed<HealthCounts>(() => data.value?.counts || {
  source_gaps: 0, subtitle_gaps: 0, failed_checks: 0, reports: 0, unverified: 0, incomplete: 0,
  approx_ratings: 0, sourceless_drafts: 0,
})
const rows = computed<HealthRow[]>(() => data.value?.results || [])
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

function when(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fa-IR', { dateStyle: 'short', timeStyle: 'short' })
}

function detailPath(row: HealthRow) {
  return `/admin/${row.target.kind === 'series' ? 'series' : 'movies'}/${row.target.id}`
}
function sitePath(row: HealthRow) {
  return `/${row.target.kind === 'series' ? 'series' : 'movies'}/${row.target.slug}`
}

// ----- Queue-wide repair --------------------------------------------------- //
// Acts on the rows on screen, not on the whole queue: an admin can see exactly
// which titles are about to be touched, and a 4,000-row queue never becomes one
// unreviewable click.
const running = ref('')

async function repairVisible(action: 'recrawl' | 'refresh_subtitles' | 'verify') {
  const byKind: Record<AdminContentKind, number[]> = { movie: [], series: [] }
  for (const row of rows.value) byKind[row.target.kind]?.push(row.target.id)
  const limit = action === 'verify' ? 20 : 250
  running.value = action
  try {
    let succeeded = 0
    let failed = 0
    for (const kind of ['movie', 'series'] as const) {
      const ids = byKind[kind].slice(0, limit)
      if (!ids.length) continue
      const response = await bulk(kind, ids, action)
      succeeded += response.succeeded
      failed += response.failed
    }
    if (failed) notify.error('بخشی انجام نشد', `${fa(succeeded)} موفق، ${fa(failed)} ناموفق`)
    else notify.success('انجام شد', `${fa(succeeded)} عنوان`)
    await refresh()
  }
  catch { notify.error('خطا', 'اجرای گروهی ناموفق بود') }
  finally { running.value = '' }
}

// ----- «بازسازی از صفر با تست» -------------------------------------------- //
const rowKey = (row: HealthRow) => `${row.target.kind}:${row.target.id}`
// One title can sit on several rows (a subtitle gap per episode); it is rebuilt once.
const pageKeys = computed(() => [...new Set(rows.value.map(rowKey))])
const allSelected = computed(() => !!pageKeys.value.length && pageKeys.value.every(key => selected.value.includes(key)))
function toggleAll() {
  selected.value = allSelected.value ? [] : [...pageKeys.value]
}
function toggleRow(row: HealthRow) {
  const key = rowKey(row)
  selected.value = selected.value.includes(key)
    ? selected.value.filter(item => item !== key)
    : [...selected.value, key]
}

/** The two «از صفر» verbs: tested on a shadow copy, or replaced outright (undoable). */
type RebuildAction = 'rebuild_staged' | 'rebuild'

// Both verbs also repair whatever put each title on this page (see title_problems.py).
const PROBLEMS_NOTE = 'مشکل ثبت‌شدهٔ هر عنوان (پخش، زیرنویس، تست، گزارش کاربر، اطلاعات ناقص، نمره) هم جداگانه رفع می‌شود.'

const REBUILD_CONFIRM: Record<RebuildAction, string> = {
  rebuild_staged: 'از صفر از همهٔ منابع روی نسخهٔ آزمایشی ساخته و تست می‌شوند.\n'
    + 'فقط عنوان‌هایی که تست را قبول کنند جایگزین می‌شوند (با نسخهٔ پشتیبان)؛ بقیه دست نمی‌خورند.\n'
    + PROBLEMS_NOTE,
  rebuild: 'بدون تست، همه‌چیز از صفر با خزنده دوباره استخراج می‌شود: اطلاعات و نمره، لینک‌های دانلود همهٔ منابع، پخش آنلاین و زیرنویس.\n'
    + 'نسخهٔ فعلی پشتیبان‌گیری می‌شود و از میز هر عنوان قابل بازگردانی است.\n'
    + PROBLEMS_NOTE,
}

async function rebuildSelected(action: RebuildAction = 'rebuild_staged') {
  const keys = selected.value
  if (!keys.length || running.value) return
  if (!window.confirm(`${fa(keys.length)} عنوان ${REBUILD_CONFIRM[action]}`)) return
  const byKind: Record<AdminContentKind, number[]> = { movie: [], series: [] }
  for (const key of keys) {
    const [kind, id] = key.split(':') as [AdminContentKind, string]
    byKind[kind]?.push(Number(id))
  }
  running.value = action
  try {
    let queued = 0
    let failed = 0
    for (const kind of ['movie', 'series'] as const) {
      if (!byKind[kind].length) continue
      const response = await bulk(kind, byKind[kind], action)
      queued += response.succeeded
      failed += response.failed
    }
    if (failed) notify.error('بخشی در صف نرفت', `${fa(queued)} در صف، ${fa(failed)} ناموفق`)
    else {
      notify.success(
        action === 'rebuild' ? 'در صف جایگزینی' : 'در صف بازسازی',
        `${fa(queued)} عنوان — نتیجه در ستون «آخرین بازسازی» می‌آید`,
      )
    }
    selected.value = []
    await refresh()
  }
  catch { notify.error('خطا', 'بازسازی گروهی در صف نرفت') }
  finally { running.value = '' }
}

// While any run on this page is still going, keep the column current.
let repairPoll: ReturnType<typeof setTimeout> | null = null
const REPAIR_POLL_MS = 10_000
watch(rows, (list) => {
  if (repairPoll) clearTimeout(repairPoll)
  repairPoll = null
  if (import.meta.client && anyRepairActive(list.map(row => row.repair)))
    repairPoll = setTimeout(() => { void refresh() }, REPAIR_POLL_MS)
}, { immediate: true })
onBeforeUnmount(() => { if (repairPoll) clearTimeout(repairPoll) })

const visibleCount = computed(() => rows.value.length)
const canPageBack = computed(() => offset.value > 0)
const canPageForward = computed(() => rows.value.length === PAGE_SIZE)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">سلامت محتوا</h1>
        <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">
          عنوان‌هایی که سامانه از پیش می‌داند مشکل دارند
        </p>
      </div>
      <button type="button" class="rv-btn rv-btn--subtle rv-focus" :disabled="pending" @click="refresh()">
        <Loader v-if="pending" class="size-4 animate-spin" />
        <RefreshCw v-else class="size-4" />
        تازه‌سازی
      </button>
    </div>

    <!-- Counts double as the queue switcher: the number is the reason to click. -->
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <button
        v-for="item in QUEUES" :key="item.key" type="button"
        class="rv-card rv-focus flex items-start justify-between gap-3 p-3.5 text-right transition"
        :style="queue === item.key
          ? { borderColor: 'var(--rv-accent)', background: 'var(--rv-accent-soft)' }
          : {}"
        @click="queue = item.key"
      >
        <span class="min-w-0">
          <span class="block text-xs font-black text-[var(--rv-text)]">{{ item.label }}</span>
          <span class="mt-0.5 block text-xs font-semibold leading-5 text-[var(--rv-muted)]">{{ item.hint }}</span>
        </span>
        <span
          class="shrink-0 text-lg font-black tabular-nums"
          :style="{ color: counts[item.key] ? 'var(--rv-danger)' : 'var(--rv-success)' }"
        >{{ fa(counts[item.key]) }}</span>
      </button>
    </div>

    <RvPanel :icon="HeartPulse" :title="QUEUES.find(q => q.key === queue)?.label || 'صف'" :padded="false">
      <template #actions>
        <button
          type="button" class="rv-btn rv-btn--primary rv-focus !min-h-8 !px-2.5 !text-xs"
          :disabled="!!running || !selected.length" :title="selected.length ? '' : 'اول عنوان‌ها را انتخاب کنید'"
          @click="rebuildSelected('rebuild_staged')"
        >
          <Loader v-if="running === 'rebuild_staged'" class="size-3.5 animate-spin" />
          <Rebuild v-else class="size-3.5" />
          بازسازی از صفر با تست
          <span v-if="selected.length" class="tabular-nums">({{ fa(selected.length) }})</span>
        </button>
        <button
          type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-8 !px-2.5 !text-xs"
          :style="{ color: 'var(--rv-danger)' }"
          :disabled="!!running || !selected.length"
          :title="selected.length ? 'بدون تست جایگزین می‌شود؛ نسخهٔ قبلی پشتیبان دارد' : 'اول عنوان‌ها را انتخاب کنید'"
          @click="rebuildSelected('rebuild')"
        >
          <Loader v-if="running === 'rebuild'" class="size-3.5 animate-spin" />
          <Rebuild v-else class="size-3.5" />
          جایگزینی از صفر بدون تست
          <span v-if="selected.length" class="tabular-nums">({{ fa(selected.length) }})</span>
        </button>
        <button
          type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
          :disabled="!!running || !visibleCount" @click="repairVisible('recrawl')"
        >
          <Loader v-if="running === 'recrawl'" class="size-3.5 animate-spin" />
          <Radar v-else class="size-3.5" />
          جستجوی دوباره برای این صفحه
        </button>
        <button
          v-if="queue === 'subtitle_gaps'"
          type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
          :disabled="!!running || !visibleCount" @click="repairVisible('refresh_subtitles')"
        >
          <Loader v-if="running === 'refresh_subtitles'" class="size-3.5 animate-spin" />
          <RefreshCw v-else class="size-3.5" />
          استخراج زیرنویس
        </button>
        <button
          v-if="queue === 'unverified' || queue === 'failed_checks'"
          type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
          :disabled="!!running || !visibleCount" @click="repairVisible('verify')"
        >
          <Loader v-if="running === 'verify'" class="size-3.5 animate-spin" />
          <ShieldCheck v-else class="size-3.5" />
          تست ۲۰ مورد اول
        </button>
      </template>

      <RvState v-if="error" kind="error" title="صف بارگذاری نشد" @retry="refresh()" />
      <RvState
        v-else-if="!pending && !rows.length"
        title="این صف خالی است"
        message="هیچ عنوانی در این دسته مشکل باز ندارد."
      />

      <div v-else class="overflow-x-auto">
        <table class="rv-table">
          <thead>
            <tr>
              <th class="w-10">
                <input
                  type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]"
                  :checked="allSelected" :disabled="!rows.length" aria-label="انتخاب همهٔ این صفحه"
                  @change="toggleAll"
                >
              </th>
              <th>عنوان</th>
              <th>نوع</th>
              <th>وضعیت</th>
              <th>جزئیات</th>
              <th>آخرین بازسازی</th>
              <th>آخرین تغییر</th>
              <th class="text-center">اقدامات</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="pending && !rows.length">
              <tr v-for="i in 6" :key="`sk${i}`">
                <td colspan="8"><div class="rv-skeleton h-8 w-full" /></td>
              </tr>
            </template>
            <tr v-for="(row, index) in rows" :key="`${row.target.kind}-${row.target.id}-${row.id ?? index}`">
              <td>
                <input
                  type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]"
                  :checked="selected.includes(rowKey(row))" :aria-label="`انتخاب ${row.target.title || row.target.id}`"
                  @change="toggleRow(row)"
                >
              </td>
              <td>
                <NuxtLink :to="detailPath(row)" class="rv-focus block max-w-[18rem] truncate font-bold text-[var(--rv-text)] hover:text-[var(--rv-accent)]">
                  {{ row.target.title || `#${fa(row.target.id)}` }}
                </NuxtLink>
              </td>
              <td><RvBadge tone="info">{{ row.target.kind === 'series' ? 'سریال' : 'فیلم' }}</RvBadge></td>
              <td>
                <RvBadge v-if="row.status" :tone="row.status === 'open' ? 'danger' : 'warning'" dot>
                  {{ row.status_label || GAP_STATUS_LABEL[row.status] || row.status }}
                </RvBadge>
                <RvBadge v-else-if="row.target.is_published === false" tone="neutral">پیش‌نویس</RvBadge>
                <span v-else class="text-[var(--rv-muted)]">—</span>
              </td>
              <td class="max-w-[22rem] truncate text-xs font-semibold text-[var(--rv-muted)]">
                <template v-if="row.gaps?.length">{{ row.gaps.map(blockerLabel).join('، ') }}</template>
                <template v-else-if="row.dead_urls !== undefined">
                  {{ fa(row.dead_urls) }} از {{ fa(row.checked_urls) }} لینک مرده
                  <span v-if="row.reason">· {{ row.reason }}</span>
                </template>
                <template v-else-if="row.problem_label">{{ row.problem_label }} — {{ row.detail }}</template>
                <template v-else-if="row.reason">{{ row.reason }}</template>
                <template v-else-if="row.link_count !== undefined">{{ fa(row.link_count) }} لینک</template>
                <template v-else>—</template>
              </td>
              <td class="whitespace-nowrap text-xs font-semibold">
                <template v-if="repairBadge(row.repair)">
                  <RvBadge :tone="repairBadge(row.repair)!.tone" dot>{{ repairBadge(row.repair)!.label }}</RvBadge>
                  <span v-if="repairBadge(row.repair)!.hint" class="mt-1 block max-w-[16rem] leading-5 text-[var(--rv-muted)]" :title="repairBadge(row.repair)!.hint">
                    {{ repairBadge(row.repair)!.hint }}
                  </span>
                </template>
                <span v-else class="text-[var(--rv-muted)]">—</span>
              </td>
              <td class="whitespace-nowrap text-xs font-bold text-[var(--rv-muted)]">
                {{ when(row.updated_at || row.checked_at) }}
              </td>
              <td>
                <div class="flex items-center justify-center gap-1">
                  <NuxtLink :to="detailPath(row)" class="rv-icon-btn rv-focus" title="میز عملیات">
                    <HeartPulse class="size-4" />
                  </NuxtLink>
                  <NuxtLink v-if="row.target.slug" :to="sitePath(row)" target="_blank" class="rv-icon-btn rv-focus" title="مشاهده در سایت">
                    <ExternalLink class="size-4" />
                  </NuxtLink>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="canPageBack || canPageForward" class="flex items-center justify-between gap-3 border-t border-[var(--rv-border)] px-4 py-3">
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="!canPageBack || pending" @click="offset = Math.max(0, offset - PAGE_SIZE)">
          قبلی
        </button>
        <span class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(visibleCount) }} ردیف</span>
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="!canPageForward || pending" @click="offset = offset + PAGE_SIZE">
          بعدی
        </button>
      </div>
    </RvPanel>
  </div>
</template>

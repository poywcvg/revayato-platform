<script setup lang="ts">
/**
 * عملیات و خزنده‌ها — the machinery behind the catalog, not the catalog.
 *
 * Everything else in the panel answers «این فیلم چه وضعی دارد؟». This page
 * answers the question that comes before it: «آیا سامانه اصلاً کار می‌کند؟».
 * Those are different failures with the same symptom — a title that never gets
 * fixed looks identical whether its repair task failed or whether no worker has
 * consumed the lane for a day — and the only way to tell them apart is to see
 * the lanes, the workers and the jobs side by side.
 *
 * Lane depth is the number that does the work here. A 50k-deep `softsub` queue
 * next to an empty `imports` queue means the crawler is idle and the subtitle
 * extractor is drowning; the reverse means something else entirely. A depth of
 * «نامشخص» means the broker itself did not answer, which the page shows rather
 * than failing, because this is precisely the page an admin opens *because*
 * something is wrong with the workers.
 */
import type { OpsJobRow } from '~/types/admin'
import Server from '~icons/lucide/server'
import Radio from '~icons/lucide/radio'
import Radar from '~icons/lucide/radar'
import Layers from '~icons/lucide/layers'
import History from '~icons/lucide/history'
import Database from '~icons/lucide/database'
import Settings from '~icons/lucide/settings'
import RefreshCw from '~icons/lucide/refresh-cw'
import Loader from '~icons/lucide/loader-circle'
import ArrowLeft from '~icons/lucide/chevron-left'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'عملیات و خزنده‌ها — روایتو' })

const { opsOverview, auditFeed } = useAdminOps()

const auditAction = ref('')

const { data, pending, error, refresh } = await useAsyncData('admin-ops', () => opsOverview())
const { data: audit, pending: auditPending, refresh: refreshAudit } = await useAsyncData(
  'admin-ops-audit',
  () => auditFeed({ limit: 30, ...(auditAction.value ? { action: auditAction.value } : {}) }),
  { watch: [auditAction] },
)

const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')
const pct = (done: number, total: number) => (total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0)

function when(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fa-IR', { dateStyle: 'short', timeStyle: 'short' })
}

const queues = computed(() => data.value?.queues || [])
const workers = computed(() => data.value?.workers)
const jobs = computed(() => data.value?.jobs)
const providers = computed(() => data.value?.providers || [])
const syncRuns = computed(() => data.value?.sync_runs || [])
const catalog = computed(() => data.value?.catalog)
const importer = computed(() => data.value?.importer_settings || {})

/** A lane nobody consumes is the failure the depth number alone cannot show. */
const consumedLanes = computed(() => {
  const set = new Set<string>()
  for (const worker of workers.value?.workers || []) for (const q of worker.queues) set.add(q)
  return set
})
function laneOrphaned(queue: string) {
  return !!workers.value?.reachable && workers.value.workers.length > 0 && !consumedLanes.value.has(queue)
}
function laneTone(depth: number | null) {
  if (depth === null) return 'neutral'
  if (depth > 5000) return 'danger'
  if (depth > 200) return 'warning'
  return 'success'
}

// Values are `MovieSyncAudit.Action` verbatim; the backend silently ignores a
// filter it does not recognise, so a typo here would look like "no history".
const AUDIT_ACTIONS: { value: string, label: string }[] = [
  { value: '', label: 'همه' },
  { value: 'import', label: 'ایمپورت' },
  { value: 'sync', label: 'همگام‌سازی' },
  { value: 'manual_create', label: 'ساخت دستی' },
  { value: 'manual_update', label: 'ویرایش دستی' },
  { value: 'archive', label: 'بایگانی' },
]

function jobProgress(job: OpsJobRow) {
  return pct(job.processed, job.total)
}

const AUTOMATION_MODE_LABEL: Record<string, string> = {
  off: 'خاموش', discover: 'فقط کشف', import: 'ایمپورت کامل',
  incremental: 'افزایشی', daily: 'روزانه', trending: 'پرطرفدارها', full: 'کامل',
}
function yesNo(value: unknown) {
  if (value === null || value === undefined) return '—'
  return value ? 'فعال' : 'غیرفعال'
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">عملیات و خزنده‌ها</h1>
        <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">
          صف‌ها، کارگرها و اجراهای ایمپورت — آخرین بروزرسانی {{ when(data?.generated_at) }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <NuxtLink to="/admin/import" class="rv-btn rv-btn--ghost rv-focus">
          کنسول ایمپورت
          <ArrowLeft class="size-4" />
        </NuxtLink>
        <button type="button" class="rv-btn rv-btn--subtle rv-focus" :disabled="pending" @click="refresh()">
          <Loader v-if="pending" class="size-4 animate-spin" />
          <RefreshCw v-else class="size-4" />
          تازه‌سازی
        </button>
      </div>
    </div>

    <RvState v-if="error" kind="error" title="اطلاعات عملیات بارگذاری نشد" @retry="refresh()" />

    <template v-else>
      <!-- Lanes first: it is the number that explains a stalled crawl. -->
      <RvPanel :icon="Layers" title="صف‌های پردازش" subtitle="تعداد کارهای منتظر در هر خط">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <template v-if="pending && !queues.length">
            <div v-for="i in 5" :key="`qs${i}`" class="rv-skeleton h-20 w-full rounded-[var(--rv-radius-sm)]" />
          </template>
          <div
            v-for="lane in queues" :key="lane.queue"
            class="rounded-[var(--rv-radius-sm)] border border-[var(--rv-border)] bg-[var(--rv-surface-2)] p-3.5"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="truncate text-xs font-black text-[var(--rv-text)]">{{ lane.label }}</p>
                <p class="mt-0.5 truncate font-mono text-[11px] font-bold text-[var(--rv-muted)]">{{ lane.queue }}</p>
              </div>
              <RvBadge :tone="laneTone(lane.depth)" dot>
                {{ lane.depth === null ? 'نامشخص' : fa(lane.depth) }}
              </RvBadge>
            </div>
            <p class="mt-2 text-xs font-semibold leading-5 text-[var(--rv-muted)]">
              {{ QUEUE_LANE_HINT[lane.queue] || '' }}
            </p>
            <p v-if="laneOrphaned(lane.queue)" class="mt-1.5 text-xs font-black" :style="{ color: 'var(--rv-danger)' }">
              هیچ کارگری این خط را نمی‌خواند
            </p>
          </div>
        </div>
      </RvPanel>

      <div class="grid gap-4 xl:grid-cols-[1fr_20rem]">
        <RvPanel :icon="Radar" title="اجراهای خزنده" :subtitle="`${fa(jobs?.active)} در حال اجرا · ${fa(jobs?.last_24h)} در ۲۴ ساعت`" :padded="false">
          <RvState
            v-if="!pending && !jobs?.recent?.length"
            title="هیچ اجرایی ثبت نشده"
            message="وقتی ایمپورتی اجرا شود، اینجا دیده می‌شود."
          />
          <div v-else class="overflow-x-auto">
            <table class="rv-table">
              <thead>
                <tr>
                  <th>منبع</th>
                  <th>وضعیت</th>
                  <th>پیشرفت</th>
                  <th>نتیجه</th>
                  <th>زمان</th>
                </tr>
              </thead>
              <tbody>
                <template v-if="pending && !jobs?.recent?.length">
                  <tr v-for="i in 5" :key="`js${i}`">
                    <td colspan="5"><div class="rv-skeleton h-7 w-full" /></td>
                  </tr>
                </template>
                <tr v-for="job in jobs?.recent || []" :key="job.id">
                  <td>
                    <p class="max-w-[12rem] truncate font-bold text-[var(--rv-text)]">{{ job.provider }}</p>
                    <p class="max-w-[12rem] truncate text-[11px] font-semibold text-[var(--rv-muted)]">{{ job.label || job.mode }}</p>
                  </td>
                  <td>
                    <RvBadge :tone="JOB_STATUS_TONE[job.status] || 'neutral'" dot>
                      {{ JOB_STATUS_LABEL[job.status] || job.status }}
                    </RvBadge>
                  </td>
                  <td class="min-w-[9rem]">
                    <div class="h-1.5 w-full overflow-hidden rounded-full bg-[var(--rv-surface-3)]">
                      <div
                        class="h-full rounded-full transition-[width]"
                        :style="{ width: `${jobProgress(job)}%`, background: 'var(--rv-accent)' }"
                      />
                    </div>
                    <p class="mt-1 text-[11px] font-bold tabular-nums text-[var(--rv-muted)]">
                      {{ fa(job.processed) }}/{{ fa(job.total) }}
                    </p>
                  </td>
                  <td class="text-xs font-bold">
                    <span :style="{ color: 'var(--rv-success)' }">{{ fa(job.matched) }} تطبیق</span>
                    <span v-if="job.failed" :style="{ color: 'var(--rv-danger)' }"> · {{ fa(job.failed) }} ناموفق</span>
                    <p v-if="job.error_message" class="max-w-[14rem] truncate text-[11px] font-semibold text-[var(--rv-muted)]">
                      {{ job.error_message }}
                    </p>
                  </td>
                  <td class="whitespace-nowrap text-xs font-bold text-[var(--rv-muted)]">{{ when(job.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </RvPanel>

        <div class="space-y-4">
          <RvPanel :icon="Radio" title="کارگرها">
            <RvBadge v-if="!workers?.reachable" tone="danger" dot>در دسترس نیست</RvBadge>
            <p v-if="!workers?.reachable" class="mt-2 text-xs leading-6 text-[var(--rv-muted)]">
              پاسخی از کارگرها نرسید. این یعنی هیچ کاری پردازش نمی‌شود — صف‌ها بالا می‌روند
              ولی چیزی از آن‌ها برداشته نمی‌شود.
            </p>
            <div v-else-if="!workers.workers.length" class="text-xs font-semibold text-[var(--rv-muted)]">
              هیچ کارگر فعالی ثبت نشده است.
            </div>
            <ul v-else class="space-y-2.5">
              <li v-for="worker in workers.workers" :key="worker.name" class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-2)] p-2.5">
                <div class="flex items-center justify-between gap-2">
                  <span class="min-w-0 flex-1 truncate font-mono text-xs font-bold text-[var(--rv-text)]">{{ worker.name }}</span>
                  <RvBadge :tone="worker.active_tasks ? 'info' : 'neutral'">{{ fa(worker.active_tasks) }} کار</RvBadge>
                </div>
                <p class="mt-1 truncate text-[11px] font-semibold text-[var(--rv-muted)]">{{ worker.queues.join('، ') || 'بدون خط' }}</p>
              </li>
            </ul>
          </RvPanel>

          <RvPanel :icon="Database" title="کاتالوگ">
            <dl class="space-y-2.5 text-xs">
              <div v-for="kind in (['movie', 'series'] as const)" :key="kind" class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-2)] p-2.5">
                <dt class="font-black text-[var(--rv-text)]">{{ kind === 'movie' ? 'فیلم‌ها' : 'سریال‌ها' }}</dt>
                <dd class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs font-bold tabular-nums text-[var(--rv-muted)]">
                  <span>کل {{ fa(catalog?.[kind]?.total) }}</span>
                  <span :style="{ color: 'var(--rv-success)' }">منتشر {{ fa(catalog?.[kind]?.published) }}</span>
                  <span>پیش‌نویس {{ fa(catalog?.[kind]?.draft) }}</span>
                  <span v-if="catalog?.[kind]?.archived !== undefined">بایگانی {{ fa(catalog?.[kind]?.archived) }}</span>
                </dd>
              </div>
            </dl>
            <NuxtLink to="/admin/health" class="rv-btn rv-btn--ghost rv-focus mt-3 w-full !text-xs">
              صف‌های مشکل ({{ fa(Object.values(data?.health || {}).reduce((a, b) => a + b, 0)) }})
            </NuxtLink>
          </RvPanel>

          <RvPanel :icon="Settings" title="تنظیمات ایمپورتر">
            <dl class="space-y-1.5 text-xs font-bold">
              <div class="flex justify-between gap-2">
                <dt class="text-[var(--rv-muted)]">انتشار خودکار</dt>
                <dd class="text-[var(--rv-text)]">{{ yesNo(importer.auto_publish) }}</dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="text-[var(--rv-muted)]">دریافت امتیاز IMDb</dt>
                <dd class="text-[var(--rv-text)]">{{ yesNo(importer.fetch_imdb_ratings) }}</dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="text-[var(--rv-muted)]">خزش خودکار</dt>
                <dd class="text-[var(--rv-text)]">{{ yesNo(importer.automation_enabled) }}</dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="text-[var(--rv-muted)]">حالت</dt>
                <dd class="text-[var(--rv-text)]">{{ AUTOMATION_MODE_LABEL[String(importer.automation_mode)] || importer.automation_mode || '—' }}</dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="text-[var(--rv-muted)]">بازهٔ اجرا</dt>
                <dd class="text-[var(--rv-text)] tabular-nums">{{ importer.automation_interval_hours ? `${fa(Number(importer.automation_interval_hours))} ساعت` : '—' }}</dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="text-[var(--rv-muted)]">سقف روزانه</dt>
                <dd class="text-[var(--rv-text)] tabular-nums">{{ importer.daily_max_pages ? `${fa(Number(importer.daily_max_pages))} صفحه` : '—' }}</dd>
              </div>
            </dl>
            <NuxtLink to="/admin/import" class="rv-btn rv-btn--ghost rv-focus mt-3 w-full !text-xs">
              تغییر تنظیمات
            </NuxtLink>
          </RvPanel>
        </div>
      </div>

      <RvPanel :icon="Server" title="منابع خزش" subtitle="سایت‌هایی که محتوا از آن‌ها برداشته می‌شود" :padded="false">
        <div class="overflow-x-auto">
          <table class="rv-table">
            <thead>
              <tr>
                <th>نام</th>
                <th>نشانی</th>
                <th>نوع</th>
                <th>سقف نرخ</th>
                <th>۲۴ ساعت</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="provider in providers" :key="provider.id">
                <td class="font-bold text-[var(--rv-text)]">{{ provider.name }}</td>
                <td class="max-w-[16rem] truncate font-mono text-[11px] text-[var(--rv-muted)]" dir="ltr">{{ provider.base_url }}</td>
                <td class="text-xs font-bold text-[var(--rv-muted)]">{{ provider.type }}</td>
                <td class="text-xs font-bold tabular-nums text-[var(--rv-muted)]">{{ fa(provider.rate_limit_per_minute) }}/دقیقه</td>
                <td class="text-xs font-bold tabular-nums text-[var(--rv-muted)]">{{ fa(provider.jobs_24h) }} اجرا</td>
                <td>
                  <RvBadge :tone="provider.is_active ? 'success' : 'neutral'" dot>
                    {{ provider.is_active ? 'فعال' : 'غیرفعال' }}
                  </RvBadge>
                </td>
              </tr>
              <tr v-if="!providers.length && !pending">
                <td colspan="6" class="py-6 text-center text-xs font-semibold text-[var(--rv-muted)]">هیچ منبعی تعریف نشده است.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </RvPanel>

      <div class="grid gap-4 lg:grid-cols-2">
        <RvPanel :icon="RefreshCw" title="همگام‌سازی کاتالوگ" subtitle="آخرین اجراهای TMDB">
          <p v-if="!syncRuns.length" class="text-xs font-semibold text-[var(--rv-muted)]">هیچ اجرایی ثبت نشده است.</p>
          <ul v-else class="space-y-2.5">
            <li v-for="run in syncRuns" :key="run.id" class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-2)] p-3">
              <div class="flex flex-wrap items-center gap-2">
                <RvBadge :tone="SYNC_RUN_TONE[run.status] || 'neutral'" dot>{{ SYNC_RUN_LABEL[run.status] || run.status }}</RvBadge>
                <span class="text-xs font-bold text-[var(--rv-text)]">{{ run.mode }}</span>
                <span class="text-[11px] font-semibold text-[var(--rv-muted)]">{{ run.phase }}</span>
                <span class="ms-auto text-[11px] font-bold text-[var(--rv-muted)]">{{ when(run.started_at) }}</span>
              </div>
              <p class="mt-1.5 text-xs font-bold tabular-nums text-[var(--rv-muted)]">
                {{ fa(run.processed) }}/{{ fa(run.total) }} · {{ fa(run.created) }} تازه · {{ fa(run.updated) }} بروز
                <span v-if="run.errors" :style="{ color: 'var(--rv-danger)' }"> · {{ fa(run.errors) }} خطا</span>
              </p>
            </li>
          </ul>
        </RvPanel>

        <RvPanel :icon="History" title="تاریخچهٔ تغییرات" subtitle="چه کسی چه چیزی را عوض کرد">
          <template #actions>
            <select v-model="auditAction" class="rv-input rv-focus !min-h-8 !w-auto !py-1 !text-xs">
              <option v-for="option in AUDIT_ACTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <button type="button" class="rv-icon-btn rv-focus" :disabled="auditPending" title="تازه‌سازی تاریخچه" @click="refreshAudit()">
              <Loader v-if="auditPending" class="size-4 animate-spin" />
              <RefreshCw v-else class="size-4" />
            </button>
          </template>
          <div v-if="auditPending" class="space-y-2">
            <div v-for="i in 5" :key="`as${i}`" class="rv-skeleton h-9 w-full rounded-[var(--rv-radius-sm)]" />
          </div>
          <p v-else-if="!audit?.results?.length" class="text-xs font-semibold text-[var(--rv-muted)]">
            هیچ تغییری با این فیلتر ثبت نشده است.
          </p>
          <ul v-else class="max-h-[26rem] space-y-2 overflow-y-auto pe-1">
            <li v-for="entry in audit.results" :key="entry.id" class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-2)] p-2.5">
              <div class="flex flex-wrap items-center gap-2">
                <RvBadge tone="violet">{{ entry.action_label || entry.action }}</RvBadge>
                <NuxtLink
                  v-if="entry.movie_id" :to="`/admin/movies/${entry.movie_id}`"
                  class="rv-focus min-w-0 flex-1 truncate text-xs font-bold text-[var(--rv-text)] hover:text-[var(--rv-accent)]"
                >
                  {{ entry.movie_title || `#${fa(entry.movie_id)}` }}
                </NuxtLink>
                <span v-else class="min-w-0 flex-1 truncate text-xs font-bold text-[var(--rv-muted)]">—</span>
                <span class="text-[11px] font-bold text-[var(--rv-muted)]">{{ when(entry.created_at) }}</span>
              </div>
              <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">
                {{ entry.actor || 'سامانه' }}
                <span v-if="entry.changed_fields?.length"> · {{ entry.changed_fields.join('، ') }}</span>
              </p>
            </li>
          </ul>
        </RvPanel>
      </div>
    </template>
  </div>
</template>

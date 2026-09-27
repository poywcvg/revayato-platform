<script setup lang="ts">
/**
 * The media desk — where a broken title gets fixed.
 *
 * The panel this replaces was read-only, with one button («خزش دوباره») and a
 * subtitle explaining that links could not be touched because only the crawler's
 * links had been tested. That reasoning was right about *why* a pasted URL is
 * dangerous and wrong about the conclusion: an admin who can see a dead mirror
 * but cannot remove it just leaves it serving errors until a crawl happens to
 * replace it.
 *
 * So links are editable here, but never on trust. Every action routes through
 * `/admin/catalog/<kind>/<id>/media/`, which runs the same identity classifier
 * and the same normalizer the importer runs — a pasted link belonging to another
 * film is refused by name, and one that survives is reported as untested until
 * a probe says otherwise. Nothing here deletes a row: «حذف» archives, and
 * removing a link edits a list the next crawl refills.
 */
import type { AdminContentKind, DeskAction, DeskLink, MediaDesk } from '~/types/admin'
import Radar from '~icons/lucide/radar'
import Loader from '~icons/lucide/loader-circle'
import ShieldCheck from '~icons/lucide/shield-check'
import Trash from '~icons/lucide/trash-2'
import Plus from '~icons/lucide/plus'
import Broom from '~icons/lucide/brush-cleaning'
import Captions from '~icons/lucide/captions'
import PlayCircle from '~icons/lucide/play-circle'
import Stethoscope from '~icons/lucide/stethoscope'
import History from '~icons/lucide/history'
import TriangleAlert from '~icons/lucide/triangle-alert'
import RefreshCw from '~icons/lucide/refresh-cw'
import CheckCheck from '~icons/lucide/check-check'

const props = defineProps<{ kind: AdminContentKind, id: number }>()
const emit = defineEmits<{ changed: [MediaDesk] }>()

const { fetchDesk, runAction } = useAdminOps()
const notify = useNotifications()

const desk = ref<MediaDesk | null>(null)
const loading = ref(true)
const failed = ref(false)
/** Which verb is in flight — one at a time, so the buttons can't race. */
const busy = ref<DeskAction | ''>('')

const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

async function load() {
  loading.value = true
  failed.value = false
  try {
    desk.value = await fetchDesk(props.kind, props.id)
  }
  catch { failed.value = true }
  finally { loading.value = false }
}

watch(() => [props.kind, props.id], () => { void load() }, { immediate: true })

/** Human-readable reasons for the refusals the backend can answer with. */
const ACTION_ERRORS: Record<string, string> = {
  contaminated_link: 'این لینک متعلق به عنوان دیگری است',
  link_rejected_by_normalizer: 'لینک پذیرفته نشد (میزبان مرده یا پسوند نامعتبر)',
  publish_blocked: 'شرایط انتشار کامل نیست',
  queue_failed: 'صف پردازش در دسترس نبود',
  action_failed: 'اجرای عملیات ناموفق بود',
  duplicate_link: 'این لینک از قبل ثبت شده است',
}

async function run(action: DeskAction, payload: Record<string, unknown> = {}, success?: string) {
  if (busy.value) return
  busy.value = action
  try {
    const response = await runAction(props.kind, props.id, action, payload)
    desk.value = response.desk
    emit('changed', response.desk)
    notify.success('انجام شد', success || 'تغییر اعمال شد')
    return response
  }
  catch (err) {
    const data = (err as { data?: { code?: string, detail?: string, blockers?: string[] } })?.data
    const blockers = (data?.blockers || []).map(blockerLabel).join('، ')
    notify.error(
      ACTION_ERRORS[data?.code || ''] || 'انجام نشد',
      blockers || data?.detail || 'سرور درخواست را نپذیرفت',
    )
    return null
  }
  finally { busy.value = '' }
}

// ----- Link editing ------------------------------------------------------- //

const adding = ref(false)
const newLink = reactive({ url: '', quality: '', label: '', season: '', episode: '' })

async function addLink() {
  const url = newLink.url.trim()
  if (!url) return
  const payload: Record<string, unknown> = { url, quality: newLink.quality.trim(), label: newLink.label.trim() }
  if (props.kind === 'series') {
    if (newLink.season) payload.season_number = Number(newLink.season)
    if (newLink.episode) payload.episode_number = Number(newLink.episode)
  }
  const response = await run('add_link', payload, 'لینک افزوده شد')
  if (response) {
    Object.assign(newLink, { url: '', quality: '', label: '', season: '', episode: '' })
    adding.value = false
  }
}

/** The second attempt, after the admin has read *why* the guard refused. */
function forceAddLink() {
  void run('add_link', {
    url: newLink.url.trim(),
    quality: newLink.quality.trim(),
    label: newLink.label.trim(),
    force: true,
  }, 'لینک با وجود هشدار افزوده شد')
}

function removeLink(link: DeskLink) {
  if (!window.confirm(`این لینک حذف شود؟\n\n${link.url}`)) return
  void run('remove_link', { url: link.url }, 'لینک حذف شد')
}

const deadCount = computed(() => (desk.value?.links || []).filter(l => l.health === 'dead').length)
const contaminated = computed(() => (desk.value?.links || []).filter(l => l.integrity?.contaminated).length)
const uncheckedCount = computed(() => (desk.value?.links || []).filter(l => l.health === 'unchecked').length)

const openReports = computed(() => desk.value?.reports?.length || 0)
const blockers = computed(() => desk.value?.publish_blockers || [])

const PLAYBACK_LABEL: Record<string, string> = {
  direct: 'پخش مستقیم',
  gateway: 'از طریق دروازه',
  unverified: 'تأیید نشده',
  none: 'بدون منبع سالم',
}
const PLAYBACK_TONE: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
  direct: 'success',
  gateway: 'info',
  unverified: 'warning',
  none: 'danger',
}
const CHECK_TONE: Record<string, 'success' | 'danger' | 'warning'> = {
  passed: 'success',
  failed: 'danger',
  unknown: 'warning',
}
const CHECK_LABEL: Record<string, string> = {
  passed: 'قبول',
  failed: 'رد',
  unknown: 'نامعلوم',
}

function when(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fa-IR', { dateStyle: 'short', timeStyle: 'short' })
}

defineExpose({ reload: load })
</script>

<template>
  <div class="space-y-5">
    <RvPanel :icon="PlayCircle" title="منابع پخش" subtitle="افزودن، حذف و تست لینک‌ها — هر تغییر ثبت می‌شود">
      <template #actions>
        <button
          type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
          :disabled="!!busy" @click="run('verify', {}, 'تست منابع انجام شد')"
        >
          <Loader v-if="busy === 'verify'" class="size-3.5 animate-spin" />
          <ShieldCheck v-else class="size-3.5" />
          تست منابع
        </button>
        <button
          type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
          :disabled="!!busy" @click="run('recrawl', { force: true }, 'خزنده‌ها دوباره فرستاده شدند')"
        >
          <Loader v-if="busy === 'recrawl'" class="size-3.5 animate-spin" />
          <Radar v-else class="size-3.5" />
          جستجوی دوباره
        </button>
      </template>

      <div v-if="loading" class="py-10 text-center text-xs font-bold text-[var(--rv-muted)]">
        در حال بارگذاری…
      </div>
      <RvState v-else-if="failed" kind="error" title="میز عملیات بارگذاری نشد" @retry="load" />

      <template v-else-if="desk">
        <!-- The verdict line: what the platform currently believes about this title. -->
        <div class="flex flex-wrap items-center gap-2">
          <RvBadge :tone="PLAYBACK_TONE[desk.playback_mode] || 'neutral'" dot>
            {{ PLAYBACK_LABEL[desk.playback_mode] || desk.playback_mode || 'نامشخص' }}
          </RvBadge>
          <RvBadge v-if="desk.check" :tone="CHECK_TONE[desk.check.status] || 'neutral'">
            تست: {{ CHECK_LABEL[desk.check.status] || desk.check.status }}
            <span v-if="desk.check.reason" class="opacity-70">· {{ desk.check.reason }}</span>
          </RvBadge>
          <RvBadge v-if="deadCount" tone="danger">{{ fa(deadCount) }} لینک مرده</RvBadge>
          <RvBadge v-if="contaminated" tone="danger">{{ fa(contaminated) }} لینک ناهمخوان</RvBadge>
          <RvBadge v-if="uncheckedCount" tone="neutral">{{ fa(uncheckedCount) }} تست‌نشده</RvBadge>
          <span class="text-xs font-bold text-[var(--rv-muted)]">
            آخرین تست: {{ when(desk.check?.checked_at) }}
          </span>
        </div>

        <!-- Repairs that only apply when there is something to repair. -->
        <div v-if="deadCount || contaminated" class="mt-3 flex flex-wrap gap-2">
          <button
            v-if="deadCount" type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-8 !text-xs"
            :disabled="!!busy" @click="run('prune_dead', {}, 'لینک‌های مرده پاک شدند')"
          >
            <Loader v-if="busy === 'prune_dead'" class="size-3.5 animate-spin" />
            <Broom v-else class="size-3.5" />
            پاکسازی لینک‌های مرده
          </button>
          <button
            v-if="contaminated" type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-8 !text-xs"
            :disabled="!!busy" @click="run('strip_contaminated', {}, 'لینک‌های ناهمخوان حذف شدند')"
          >
            <Loader v-if="busy === 'strip_contaminated'" class="size-3.5 animate-spin" />
            <Trash v-else class="size-3.5" />
            حذف لینک‌های ناهمخوان
          </button>
        </div>

        <RvState
          v-if="!desk.links.length"
          title="لینکی ثبت نشده"
          message="«جستجوی دوباره» را بزنید تا خزنده‌ها منابع این عنوان را پیدا کنند، یا لینک را دستی اضافه کنید."
        />
        <ul v-else class="mt-3 divide-y divide-[var(--rv-border)]">
          <li v-for="link in desk.links" :key="link.index" class="py-2.5 first:pt-0">
            <div class="flex flex-wrap items-center gap-2">
              <RvBadge :tone="LINK_HEALTH_TONE[link.health] || 'neutral'" dot>
                {{ LINK_HEALTH_LABEL[link.health] || link.health }}
              </RvBadge>
              <RvBadge v-if="link.quality" tone="neutral">{{ link.quality }}</RvBadge>
              <RvBadge v-if="link.season_number" tone="info">
                فصل {{ fa(link.season_number) }} · قسمت {{ fa(link.episode_number) }}
              </RvBadge>
              <RvBadge v-if="link.browser_safe === false" tone="warning">
                نیازمند دروازه<span v-if="link.container"> · {{ link.container }}</span>
              </RvBadge>
              <span class="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--rv-muted)]" dir="ltr">
                {{ link.url || link.label }}
              </span>
              <button
                type="button"
                class="rv-btn rv-btn--subtle rv-focus !min-h-7 !px-2 !text-xs"
                :disabled="!!busy"
                aria-label="حذف لینک"
                @click="removeLink(link)"
              >
                <Trash class="size-3.5" />
              </button>
            </div>
            <p v-if="link.reason || link.integrity?.contaminated" class="mt-1 text-xs font-bold" :style="{ color: link.integrity?.contaminated ? 'var(--rv-danger)' : 'var(--rv-muted)' }">
              <template v-if="link.integrity?.contaminated">
                {{ INTEGRITY_LABEL[link.integrity.category] || link.integrity.category }}
              </template>
              <template v-else>{{ link.reason }}</template>
            </p>
          </li>
        </ul>

        <!-- Manual link entry. Held behind a disclosure because it is the
             exception: the crawler is still the normal way links arrive. -->
        <div class="mt-4 border-t border-[var(--rv-border)] pt-3">
          <button
            v-if="!adding" type="button"
            class="rv-btn rv-btn--ghost rv-focus !min-h-8 !text-xs"
            @click="adding = true"
          >
            <Plus class="size-3.5" /> افزودن لینک دستی
          </button>
          <div v-else class="space-y-2">
            <input v-model="newLink.url" dir="ltr" class="rv-input" placeholder="https://…" >
            <div class="grid grid-cols-2 gap-2" :class="kind === 'series' ? 'sm:grid-cols-4' : ''">
              <input v-model="newLink.quality" class="rv-input" placeholder="کیفیت (1080p)">
              <input v-model="newLink.label" class="rv-input" placeholder="برچسب">
              <template v-if="kind === 'series'">
                <input v-model="newLink.season" class="rv-input" placeholder="فصل" inputmode="numeric">
                <input v-model="newLink.episode" class="rv-input" placeholder="قسمت" inputmode="numeric">
              </template>
            </div>
            <p class="text-xs font-semibold leading-5 text-[var(--rv-muted)]">
              لینک پیش از ذخیره با همان سنجهٔ ایمپورتر بررسی می‌شود: اگر متعلق به عنوان دیگری باشد رد می‌شود.
              تا زمانی که «تست منابع» اجرا نشود، وضعیتش «تست‌نشده» می‌ماند.
            </p>
            <div class="flex flex-wrap gap-2">
              <button type="button" class="rv-btn rv-btn--primary rv-focus !min-h-8 !text-xs" :disabled="!!busy || !newLink.url.trim()" @click="addLink">
                <Loader v-if="busy === 'add_link'" class="size-3.5 animate-spin" />
                <Plus v-else class="size-3.5" />
                افزودن
              </button>
              <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-8 !text-xs" :disabled="!!busy" @click="forceAddLink">
                افزودن با نادیده‌گرفتن هشدار
              </button>
              <button type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !text-xs" @click="adding = false">
                انصراف
              </button>
            </div>
          </div>
        </div>
      </template>
    </RvPanel>

    <!-- Subtitles: movies only. A series' subtitles live on its episodes. -->
    <RvPanel v-if="desk && kind === 'movie'" :icon="Captions" title="زیرنویس‌ها" :subtitle="`${fa(desk.subtitles.length)} مسیر ثبت‌شده`">
      <template #actions>
        <button
          type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
          :disabled="!!busy" @click="run('refresh_subtitles', {}, 'استخراج زیرنویس در صف قرار گرفت')"
        >
          <Loader v-if="busy === 'refresh_subtitles'" class="size-3.5 animate-spin" />
          <RefreshCw v-else class="size-3.5" />
          استخراج دوباره
        </button>
      </template>
      <RvState
        v-if="!desk.subtitles.length"
        title="زیرنویسی ثبت نشده"
        :message="desk.is_published ? '«استخراج دوباره» کارگر زیرنویس را برای این عنوان صدا می‌زند.' : 'این عنوان منتشر نشده؛ کارگر زیرنویس فقط روی عنوان‌های منتشرشده کار می‌کند.'"
      />
      <ul v-else class="divide-y divide-[var(--rv-border)]">
        <li v-for="track in desk.subtitles" :key="track.index" class="flex flex-wrap items-center gap-2 py-2 first:pt-0">
          <RvBadge tone="neutral">{{ track.lang || '—' }}</RvBadge>
          <span class="text-xs font-black text-[var(--rv-text)]">{{ track.label }}</span>
          <span class="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--rv-muted)]" dir="ltr">{{ track.src }}</span>
          <button
            type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-7 !px-2 !text-xs"
            :disabled="!!busy" aria-label="حذف زیرنویس"
            @click="run('remove_subtitle', { index: track.index }, 'زیرنویس حذف شد')"
          >
            <Trash class="size-3.5" />
          </button>
        </li>
      </ul>
    </RvPanel>

    <!-- Everything the platform already knows is wrong with this title. -->
    <RvPanel
      v-if="desk && (desk.source_gap || desk.subtitle_gap || openReports || blockers.length || desk.diagnosis?.unplayable)"
      :icon="Stethoscope" title="تشخیص و مشکلات باز"
    >
      <template #actions>
        <button
          v-if="desk.source_gap || desk.subtitle_gap"
          type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
          :disabled="!!busy" @click="run('resolve_gaps', {}, 'مشکلات باز بسته شدند')"
        >
          <Loader v-if="busy === 'resolve_gaps'" class="size-3.5 animate-spin" />
          <CheckCheck v-else class="size-3.5" />
          علامت‌گذاری به‌عنوان حل‌شده
        </button>
      </template>

      <div class="space-y-3 text-xs">
        <div v-if="blockers.length" class="flex flex-wrap items-center gap-2">
          <span class="font-black text-[var(--rv-text)]">مانع انتشار:</span>
          <RvBadge v-for="key in blockers" :key="key" tone="warning">{{ blockerLabel(key) }}</RvBadge>
        </div>
        <div v-if="desk.diagnosis?.unplayable" class="flex items-start gap-2 rounded-[var(--rv-radius-sm)] p-2.5" :style="{ background: 'var(--rv-danger-soft)', color: 'var(--rv-danger)' }">
          <TriangleAlert class="mt-0.5 size-4 shrink-0" />
          <p class="font-bold leading-6">
            هیچ منبع سازگار با مرورگر ندارد ({{ desk.diagnosis.reason || 'نامشخص' }})<span v-if="desk.diagnosis.containers?.length"> — {{ desk.diagnosis.containers.join('، ') }}</span>
          </p>
        </div>
        <div v-if="desk.source_gap" class="flex flex-wrap items-center gap-2">
          <span class="font-black text-[var(--rv-text)]">کمبود منبع:</span>
          <RvBadge tone="danger">{{ GAP_STATUS_LABEL[desk.source_gap.status] || desk.source_gap.status }}</RvBadge>
          <span class="font-semibold text-[var(--rv-muted)]">{{ desk.source_gap.reason }} · {{ fa(desk.source_gap.report_count) }} گزارش</span>
        </div>
        <div v-if="desk.subtitle_gap" class="flex flex-wrap items-center gap-2">
          <span class="font-black text-[var(--rv-text)]">کمبود زیرنویس:</span>
          <RvBadge tone="warning">{{ GAP_STATUS_LABEL[desk.subtitle_gap.status] || desk.subtitle_gap.status }}</RvBadge>
          <span class="font-semibold text-[var(--rv-muted)]">{{ fa(desk.subtitle_gap.report_count) }} گزارش</span>
        </div>
        <ul v-if="openReports" class="divide-y divide-[var(--rv-border)]">
          <li v-for="report in desk.reports" :key="report.id" class="flex flex-wrap items-center gap-2 py-2">
            <RvBadge tone="neutral">{{ report.problem_label }}</RvBadge>
            <RvBadge tone="info">{{ report.status_label }}</RvBadge>
            <span v-if="report.episode_number" class="text-xs font-bold text-[var(--rv-muted)]">
              فصل {{ fa(report.season_number) }} · قسمت {{ fa(report.episode_number) }}
            </span>
            <span class="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--rv-muted)]">{{ report.detail }}</span>
            <span class="text-xs font-bold text-[var(--rv-muted)]">×{{ fa(report.report_count) }}</span>
          </li>
        </ul>
      </div>
    </RvPanel>

    <!-- Per-episode state: the whole reason a series desk is different from a movie's. -->
    <RvPanel v-if="desk && desk.episodes?.length" :icon="PlayCircle" title="قسمت‌ها" :subtitle="`${fa(desk.episodes.length)} قسمت`">
      <div class="max-h-96 overflow-y-auto">
        <table class="w-full text-right text-xs">
          <thead class="sticky top-0 bg-[var(--rv-surface-2)] text-[var(--rv-muted)]">
            <tr>
              <th class="py-2 font-black">قسمت</th>
              <th class="py-2 font-black">عنوان</th>
              <th class="py-2 font-black">پخش</th>
              <th class="py-2 font-black">لینک</th>
              <th class="py-2 font-black">زیرنویس</th>
              <th class="py-2 font-black">تست</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-[var(--rv-border)]">
            <tr v-for="ep in desk.episodes" :key="ep.id">
              <td class="py-2 font-bold text-[var(--rv-text)]">S{{ fa(ep.season_number) }}E{{ fa(ep.episode_number) }}</td>
              <td class="max-w-[16rem] truncate py-2 font-semibold text-[var(--rv-muted)]">{{ ep.title }}</td>
              <td class="py-2">
                <RvBadge :tone="ep.has_stream ? 'success' : 'danger'" dot>
                  {{ ep.has_stream ? 'دارد' : 'ندارد' }}
                </RvBadge>
              </td>
              <td class="py-2 font-bold" :style="{ color: ep.dead_links ? 'var(--rv-danger)' : 'var(--rv-muted)' }">
                {{ fa(ep.link_count) }}<span v-if="ep.dead_links"> ({{ fa(ep.dead_links) }} مرده)</span>
              </td>
              <td class="py-2 font-bold text-[var(--rv-muted)]">{{ fa(ep.subtitle_count) }}</td>
              <td class="py-2">
                <RvBadge v-if="ep.check" :tone="CHECK_TONE[ep.check.status] || 'neutral'">
                  {{ CHECK_LABEL[ep.check.status] || ep.check.status }}
                </RvBadge>
                <span v-else class="text-[var(--rv-muted)]">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </RvPanel>

    <!-- Crawler runs aimed at this title, so «چرا لینکی نیامد؟» has an answer. -->
    <RvPanel v-if="desk?.jobs?.length" :icon="Radar" title="اجراهای خزنده" subtitle="جدیدترین اجراها برای همین عنوان">
      <ul class="divide-y divide-[var(--rv-border)] text-xs">
        <li v-for="job in desk.jobs" :key="job.id" class="flex flex-wrap items-center gap-2 py-2 first:pt-0">
          <RvBadge :tone="job.status === 'completed' ? 'success' : job.status === 'failed' ? 'danger' : 'info'" dot>
            {{ job.status }}
          </RvBadge>
          <span class="font-bold text-[var(--rv-muted)]">{{ job.mode }}</span>
          <span class="min-w-0 flex-1 truncate font-semibold" :style="{ color: job.error_message ? 'var(--rv-danger)' : 'var(--rv-muted)' }">
            {{ job.error_message || '—' }}
          </span>
          <span class="font-bold text-[var(--rv-muted)]">{{ when(job.created_at) }}</span>
        </li>
      </ul>
    </RvPanel>

    <!-- Who changed what. The panel's answer to "why is this gone?". -->
    <RvPanel v-if="desk?.audits?.length" :icon="History" title="تاریخچهٔ تغییرات">
      <ul class="divide-y divide-[var(--rv-border)] text-xs">
        <li v-for="entry in desk.audits" :key="entry.id" class="flex flex-wrap items-center gap-2 py-2 first:pt-0">
          <RvBadge tone="neutral">{{ entry.action_label }}</RvBadge>
          <span class="font-black text-[var(--rv-text)]">{{ entry.actor || 'سیستم' }}</span>
          <span class="min-w-0 flex-1 truncate font-semibold text-[var(--rv-muted)]">
            {{ (entry.details as Record<string, unknown>)?.reason || entry.changed_fields.join('، ') || '—' }}
          </span>
          <span class="font-bold text-[var(--rv-muted)]">{{ when(entry.created_at) }}</span>
        </li>
      </ul>
    </RvPanel>
  </div>
</template>

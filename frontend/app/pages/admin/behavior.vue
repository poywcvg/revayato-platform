<script setup lang="ts">
import type {
  AnalyticsEnvelope,
  AnalyticsBehaviorData,
  AnalyticsPeriodKey,
  AnalyticsNamedValue,
} from '~/types/analytics'
import Activity from '~icons/lucide/activity'
import Users from '~icons/lucide/users-round'
import Radio from '~icons/lucide/radio'
import PlayCircle from '~icons/lucide/circle-play'
import MousePointerClick from '~icons/lucide/mouse-pointer-click'
import Search from '~icons/lucide/search'
import Repeat from '~icons/lucide/repeat'
import Layers from '~icons/lucide/layers'
import Filter from '~icons/lucide/funnel'
import CalendarClock from '~icons/lucide/calendar-clock'
import Trophy from '~icons/lucide/trophy'
import Sparkles from '~icons/lucide/sparkles'
import RefreshCw from '~icons/lucide/refresh-cw'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'تحلیل رفتار کاربر — روایتو' })

const { api } = useApi()

const PERIODS: { key: AnalyticsPeriodKey, label: string }[] = [
  { key: '7d', label: '۷ روز' },
  { key: '30d', label: '۳۰ روز' },
  { key: '90d', label: '۹۰ روز' },
]
const period = ref<AnalyticsPeriodKey>('30d')

const { data, pending, error, refresh } = await useAsyncData(
  'admin-behavior',
  () => api<AnalyticsEnvelope<AnalyticsBehaviorData>>('/analytics/behavior/', { query: { period: period.value } }),
  { watch: [period] },
)

const d = computed(() => data.value?.data ?? null)
const summary = computed(() => d.value?.summary ?? null)
const funnel = computed(() => d.value?.funnel ?? null)
const discovery = computed(() => d.value?.discovery ?? null)
const sessions = computed(() => d.value?.sessions ?? null)
const retention = computed(() => d.value?.retention ?? null)
const realtime = computed(() => d.value?.realtime ?? null)

const generatedAt = computed(() => {
  const ts = data.value?.generated_at
  if (!ts) return ''
  try {
    return new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit' }).format(new Date(ts))
  }
  catch { return '' }
})

const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')
const pct = (n: number | null | undefined) => (n == null ? '—' : `${(n).toLocaleString('fa-IR')}٪`)

// ---- Funnel: color per stage, bar width from pct_of_top ----
const FUNNEL_TONES = ['var(--rv-info)', 'var(--rv-accent)', 'var(--rv-violet)', 'var(--rv-success)']

// ---- Generic bar scaling ----
function maxValue(rows: AnalyticsNamedValue[] | undefined) {
  return Math.max(1, ...(rows ?? []).map(r => r.value))
}
const actionMax = computed(() => maxValue(d.value?.action_mix))
const interestMax = computed(() => maxValue(d.value?.content_interest))
const depthMax = computed(() => maxValue(sessions.value?.depth_distribution))

// ---- Heatmap ----
const heatmap = computed(() => d.value?.heatmap ?? null)
const heatMax = computed(() => Math.max(1, ...(heatmap.value?.cells ?? []).map(c => c.value)))
function heatCell(weekday: number, hour: number) {
  return heatmap.value?.cells.find(c => c.weekday === weekday && c.hour === hour)?.value ?? 0
}
function heatStyle(value: number) {
  if (!value) return { background: 'var(--rv-surface-3)' }
  const t = Math.min(1, value / heatMax.value)
  // ease so low values stay visible
  const alpha = 0.12 + Math.sqrt(t) * 0.88
  return { background: `color-mix(in srgb, var(--rv-accent) ${Math.round(alpha * 100)}%, transparent)` }
}
const CONTENT_TONES: Record<string, string> = {
  movie: 'var(--rv-info)',
  series: 'var(--rv-violet)',
  episode: 'var(--rv-accent)',
  actor: 'var(--rv-success)',
  director: 'var(--rv-warning)',
  genre: 'var(--rv-danger)',
  search: 'var(--rv-muted)',
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">تحلیل رفتار کاربر</h1>
        <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">
          مسیر واقعی کاربران از کشف تا تماشا · داده‌ی زنده
          <span v-if="generatedAt"> · بروزرسانی {{ generatedAt }}</span>
        </p>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex rounded-[var(--rv-radius-full)] border border-[var(--rv-border)] bg-[var(--rv-surface)] p-1">
          <button
            v-for="p in PERIODS"
            :key="p.key"
            type="button"
            class="rv-focus rounded-[var(--rv-radius-full)] px-3 py-1.5 text-xs font-black transition"
            :class="period === p.key
              ? 'bg-[var(--rv-accent)] text-[var(--rv-on-accent)]'
              : 'text-[var(--rv-muted)] hover:text-[var(--rv-text)]'"
            @click="period = p.key"
          >
            {{ p.label }}
          </button>
        </div>
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9 !px-2.5" :disabled="pending" title="بروزرسانی" @click="refresh()">
          <RefreshCw class="size-4" :class="pending ? 'animate-spin' : ''" />
        </button>
      </div>
    </div>

    <RvState v-if="error" kind="error" title="خطا در دریافت آمار" message="ارتباط با سرور برقرار نشد." @retry="refresh()" />

    <template v-else>
      <!-- Realtime strip -->
      <div class="rv-card rv-card--glass flex flex-wrap items-center gap-x-8 gap-y-3 p-4">
        <div class="flex items-center gap-2.5">
          <span class="relative flex size-2.5">
            <span class="absolute inline-flex size-full animate-ping rounded-full bg-[var(--rv-success)] opacity-75" />
            <span class="relative inline-flex size-2.5 rounded-full bg-[var(--rv-success)]" />
          </span>
          <span class="text-xs font-black text-[var(--rv-muted)]">زنده</span>
        </div>
        <div class="flex items-center gap-2.5">
          <Users class="size-4 text-[var(--rv-info)]" />
          <span class="text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(realtime?.online_total ?? realtime?.online_users) }}</span>
          <span class="text-xs font-semibold text-[var(--rv-muted)]">آنلاین</span>
        </div>
        <div class="flex items-center gap-2.5">
          <Radio class="size-4 text-[var(--rv-accent)]" />
          <span class="text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(realtime?.live_watch_sessions) }}</span>
          <span class="text-xs font-semibold text-[var(--rv-muted)]">تماشای همزمان</span>
        </div>
      </div>

      <!-- Summary KPIs -->
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <RvStat label="رویدادهای ثبت‌شده" :value="summary?.tracked_events ?? null" :icon="Activity" tone="accent" :loading="pending && !summary" hint="کل تعامل‌های بازه" />
        <RvStat label="کاربران فعال" :value="summary?.active_users ?? null" :icon="Users" tone="info" :loading="pending && !summary" :hint="`${fa(summary?.anonymous_sessions)} نشست مهمان`" />
        <RvStat label="رویداد به ازای هر کاربر" :value="summary?.events_per_active ?? null" format="raw" :icon="Sparkles" tone="violet" :loading="pending && !summary" hint="میانگین عمق تعامل" />
        <RvStat label="نرخ تماشای کامل" :value="funnel?.completion_rate ?? null" format="percent" :icon="PlayCircle" tone="success" :loading="pending && !funnel" hint="از شروع پخش تا پایان" />
      </div>

      <!-- Funnel + Discovery -->
      <div class="grid gap-4 lg:grid-cols-3">
        <!-- Behavior funnel -->
        <RvPanel title="قیف رفتار" subtitle="از بازدید صفحه تا تماشای کامل" :icon="Filter" class="lg:col-span-2">
          <RvState v-if="!pending && !funnel?.stages?.length" title="داده‌ای نیست" message="در این بازه رویدادی ثبت نشده." />
          <ul v-else class="space-y-3">
            <li v-for="(stage, i) in funnel?.stages ?? []" :key="stage.id">
              <div class="mb-1 flex items-baseline justify-between gap-2">
                <span class="text-xs font-black text-[var(--rv-text)]">{{ stage.label }}</span>
                <span class="flex items-baseline gap-2">
                  <span class="text-sm font-black tabular-nums text-[var(--rv-text)]">{{ fa(stage.value) }}</span>
                  <span v-if="stage.step_conversion != null" class="text-[11px] font-black tabular-nums text-[var(--rv-muted)]">
                    {{ pct(stage.step_conversion) }} تبدیل
                  </span>
                </span>
              </div>
              <div class="h-3 w-full overflow-hidden rounded-full bg-[var(--rv-surface-3)]">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :style="{ width: `${stage.pct_of_top ?? 0}%`, background: FUNNEL_TONES[i % FUNNEL_TONES.length] }"
                />
              </div>
            </li>
          </ul>
          <div class="mt-4 grid grid-cols-2 gap-3 border-t border-[var(--rv-border)] pt-4">
            <div class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface)] px-3 py-2.5">
              <p class="text-xs font-bold text-[var(--rv-muted)]">نرخ شروع پخش</p>
              <p class="mt-0.5 text-lg font-black tabular-nums text-[var(--rv-text)]">{{ pct(funnel?.play_through_rate) }}</p>
            </div>
            <div class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface)] px-3 py-2.5">
              <p class="text-xs font-bold text-[var(--rv-muted)]">نرخ تکمیل تماشا</p>
              <p class="mt-0.5 text-lg font-black tabular-nums text-[var(--rv-text)]">{{ pct(funnel?.completion_rate) }}</p>
            </div>
          </div>
        </RvPanel>

        <!-- Discovery / search CTR -->
        <RvPanel title="کشف و جستجو" subtitle="از جستجو تا کلیک روی نتیجه" :icon="Search">
          <RvState v-if="!pending && !discovery?.searches" title="جستجویی نبوده" message="در این بازه جستجویی ثبت نشده." />
          <template v-else>
            <div class="grid grid-cols-2 gap-3">
              <div class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface)] px-3 py-2.5">
                <div class="flex items-center gap-1.5 text-[var(--rv-muted)]"><Search class="size-3.5" /><span class="text-xs font-bold">جستجو</span></div>
                <p class="mt-0.5 text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(discovery?.searches) }}</p>
              </div>
              <div class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface)] px-3 py-2.5">
                <div class="flex items-center gap-1.5 text-[var(--rv-muted)]"><MousePointerClick class="size-3.5" /><span class="text-xs font-bold">کلیک نتیجه</span></div>
                <p class="mt-0.5 text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(discovery?.result_clicks) }}</p>
              </div>
            </div>
            <div class="mt-3 space-y-2.5">
              <div>
                <div class="mb-1 flex justify-between text-xs font-bold"><span class="text-[var(--rv-muted)]">نرخ کلیک (CTR)</span><span class="tabular-nums text-[var(--rv-text)]">{{ pct(discovery?.click_through_rate) }}</span></div>
                <div class="h-2 overflow-hidden rounded-full bg-[var(--rv-surface-3)]"><div class="h-full rounded-full bg-[var(--rv-success)]" :style="{ width: `${Math.min(100, discovery?.click_through_rate ?? 0)}%` }" /></div>
              </div>
              <div>
                <div class="mb-1 flex justify-between text-xs font-bold"><span class="text-[var(--rv-muted)]">جستجوی بدون نتیجه</span><span class="tabular-nums text-[var(--rv-text)]">{{ pct(discovery?.zero_result_rate) }}</span></div>
                <div class="h-2 overflow-hidden rounded-full bg-[var(--rv-surface-3)]"><div class="h-full rounded-full bg-[var(--rv-danger)]" :style="{ width: `${Math.min(100, discovery?.zero_result_rate ?? 0)}%` }" /></div>
              </div>
            </div>
            <div v-if="discovery?.top_terms?.length" class="mt-4 border-t border-[var(--rv-border)] pt-3">
              <p class="mb-2 text-xs font-black text-[var(--rv-muted)]">پرجستجوترین‌ها</p>
              <ul class="space-y-1.5">
                <li v-for="term in discovery.top_terms.slice(0, 6)" :key="term.term" class="flex items-center justify-between gap-2 text-xs">
                  <span class="min-w-0 flex-1 truncate font-bold text-[var(--rv-text)]">{{ term.term }}</span>
                  <span v-if="term.zero_result_count" class="shrink-0"><RvBadge tone="danger">بدون نتیجه</RvBadge></span>
                  <span class="shrink-0 tabular-nums font-black text-[var(--rv-muted)]">{{ fa(term.count) }}</span>
                </li>
              </ul>
            </div>
          </template>
        </RvPanel>
      </div>

      <!-- Session depth + Retention -->
      <div class="grid gap-4 lg:grid-cols-2">
        <!-- Session depth -->
        <RvPanel title="عمق نشست‌ها" subtitle="کیفیت هر بازدید" :icon="Layers">
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <p class="text-xs font-bold text-[var(--rv-muted)]">نشست‌ها</p>
              <p class="text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(sessions?.sessions) }}</p>
            </div>
            <div>
              <p class="text-xs font-bold text-[var(--rv-muted)]">میانگین رویداد</p>
              <p class="text-lg font-black tabular-nums text-[var(--rv-text)]">{{ (sessions?.avg_events_per_session ?? 0).toLocaleString('fa-IR') }}</p>
            </div>
            <div>
              <p class="text-xs font-bold text-[var(--rv-muted)]">مدت میانگین</p>
              <p class="text-lg font-black tabular-nums text-[var(--rv-text)]">{{ (sessions?.avg_duration_minutes ?? 0).toLocaleString('fa-IR') }}<span class="text-xs font-bold text-[var(--rv-muted)]"> دقیقه</span></p>
            </div>
            <div>
              <p class="text-xs font-bold text-[var(--rv-muted)]">نرخ پرش</p>
              <p class="text-lg font-black tabular-nums text-[var(--rv-text)]">{{ pct(sessions?.bounce_rate) }}</p>
            </div>
          </div>
          <div class="mt-4 border-t border-[var(--rv-border)] pt-3">
            <p class="mb-2 text-xs font-black text-[var(--rv-muted)]">توزیع عمق (رویداد در نشست)</p>
            <ul class="space-y-2">
              <li v-for="row in sessions?.depth_distribution ?? []" :key="row.id" class="flex items-center gap-2.5">
                <span class="w-14 shrink-0 text-xs font-bold text-[var(--rv-muted)]">{{ row.label }}</span>
                <div class="h-2.5 flex-1 overflow-hidden rounded-full bg-[var(--rv-surface-3)]">
                  <div class="h-full rounded-full bg-[var(--rv-violet)]" :style="{ width: `${(row.value / depthMax) * 100}%` }" />
                </div>
                <span class="w-10 shrink-0 text-left text-xs font-black tabular-nums text-[var(--rv-text)]">{{ fa(row.value) }}</span>
              </li>
            </ul>
          </div>
        </RvPanel>

        <!-- Retention -->
        <RvPanel title="ماندگاری و چسبندگی" subtitle="بازگشت کاربران واقعی" :icon="Repeat">
          <div class="grid grid-cols-3 gap-3">
            <div class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface)] px-3 py-2.5 text-center">
              <p class="text-xs font-bold text-[var(--rv-muted)]">روزانه</p>
              <p class="mt-0.5 text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(retention?.dau) }}</p>
            </div>
            <div class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface)] px-3 py-2.5 text-center">
              <p class="text-xs font-bold text-[var(--rv-muted)]">هفتگی</p>
              <p class="mt-0.5 text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(retention?.wau) }}</p>
            </div>
            <div class="rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface)] px-3 py-2.5 text-center">
              <p class="text-xs font-bold text-[var(--rv-muted)]">ماهانه</p>
              <p class="mt-0.5 text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(retention?.mau) }}</p>
            </div>
          </div>
          <div class="mt-3 space-y-3">
            <div>
              <div class="mb-1 flex justify-between text-xs font-bold"><span class="text-[var(--rv-muted)]">چسبندگی (DAU/MAU)</span><span class="tabular-nums text-[var(--rv-text)]">{{ pct(retention?.stickiness) }}</span></div>
              <div class="h-2 overflow-hidden rounded-full bg-[var(--rv-surface-3)]"><div class="h-full rounded-full bg-[var(--rv-accent)]" :style="{ width: `${Math.min(100, retention?.stickiness ?? 0)}%` }" /></div>
            </div>
            <div>
              <div class="mb-1 flex justify-between text-xs font-bold"><span class="text-[var(--rv-muted)]">بازگشت هفته‌به‌هفته</span><span class="tabular-nums text-[var(--rv-text)]">{{ pct(retention?.wow_retention_rate) }}</span></div>
              <div class="h-2 overflow-hidden rounded-full bg-[var(--rv-surface-3)]"><div class="h-full rounded-full bg-[var(--rv-info)]" :style="{ width: `${Math.min(100, retention?.wow_retention_rate ?? 0)}%` }" /></div>
              <p class="mt-1 text-[11px] font-semibold text-[var(--rv-faint)]">{{ fa(retention?.wow_retained) }} از {{ fa(retention?.wow_prior_cohort) }} کاربر فعالِ هفته‌ی قبل بازگشتند</p>
            </div>
          </div>
        </RvPanel>
      </div>

      <!-- Action mix + content interest -->
      <div class="grid gap-4 lg:grid-cols-2">
        <RvPanel title="ترکیب کنش‌ها" subtitle="کاربران بیشتر چه می‌کنند" :icon="Activity">
          <RvState v-if="!pending && !d?.action_mix?.length" title="داده‌ای نیست" message="رویدادی ثبت نشده." />
          <ul v-else class="space-y-2">
            <li v-for="row in d?.action_mix ?? []" :key="row.id" class="flex items-center gap-2.5">
              <span class="w-24 shrink-0 truncate text-xs font-bold text-[var(--rv-muted)]">{{ row.label }}</span>
              <div class="h-2.5 flex-1 overflow-hidden rounded-full bg-[var(--rv-surface-3)]">
                <div class="h-full rounded-full bg-[var(--rv-accent)]" :style="{ width: `${(row.value / actionMax) * 100}%` }" />
              </div>
              <span class="w-12 shrink-0 text-left text-xs font-black tabular-nums text-[var(--rv-text)]">{{ fa(row.value) }}</span>
            </li>
          </ul>
        </RvPanel>

        <RvPanel title="کانون توجه" subtitle="تعامل بر اساس نوع محتوا" :icon="Layers">
          <RvState v-if="!pending && !d?.content_interest?.length" title="داده‌ای نیست" message="رویدادی ثبت نشده." />
          <ul v-else class="space-y-2">
            <li v-for="row in d?.content_interest ?? []" :key="row.id" class="flex items-center gap-2.5">
              <span class="w-20 shrink-0 truncate text-xs font-bold text-[var(--rv-muted)]">{{ row.label }}</span>
              <div class="h-2.5 flex-1 overflow-hidden rounded-full bg-[var(--rv-surface-3)]">
                <div class="h-full rounded-full" :style="{ width: `${(row.value / interestMax) * 100}%`, background: CONTENT_TONES[row.id ?? ''] ?? 'var(--rv-muted)' }" />
              </div>
              <span class="w-12 shrink-0 text-left text-xs font-black tabular-nums text-[var(--rv-text)]">{{ fa(row.value) }}</span>
            </li>
          </ul>
        </RvPanel>
      </div>

      <!-- Activity heatmap -->
      <RvPanel title="نقشه‌ی حرارتی فعالیت" subtitle="ساعت‌های اوج تعامل در هفته" :icon="CalendarClock" :padded="false">
        <RvState v-if="!pending && !heatmap?.cells?.length" title="داده‌ای نیست" message="فعالیتی ثبت نشده." />
        <div v-else class="overflow-x-auto p-4">
          <div class="min-w-[640px]">
            <div class="flex gap-1 pr-12 text-[11px] font-bold text-[var(--rv-faint)]">
              <span v-for="h in 24" :key="h" class="flex-1 text-center">{{ (h - 1) % 3 === 0 ? fa(h - 1) : '' }}</span>
            </div>
            <div v-for="wd in heatmap?.weekdays ?? []" :key="wd.id" class="mt-1 flex items-center gap-1">
              <span class="w-11 shrink-0 text-[11px] font-bold text-[var(--rv-muted)]">{{ wd.label }}</span>
              <div class="flex flex-1 gap-1">
                <span
                  v-for="h in 24"
                  :key="h"
                  class="aspect-square flex-1 rounded-[3px] transition"
                  :style="heatStyle(heatCell(wd.id, h - 1))"
                  :title="`${wd.label} · ${fa(h - 1)}:۰۰ — ${fa(heatCell(wd.id, h - 1))} رویداد`"
                />
              </div>
            </div>
            <div class="mt-3 flex items-center justify-end gap-1.5 text-[11px] font-bold text-[var(--rv-faint)]">
              <span>کم</span>
              <span class="size-3 rounded-[3px]" :style="heatStyle(0)" />
              <span class="size-3 rounded-[3px]" :style="heatStyle(heatMax * 0.25)" />
              <span class="size-3 rounded-[3px]" :style="heatStyle(heatMax * 0.6)" />
              <span class="size-3 rounded-[3px]" :style="heatStyle(heatMax)" />
              <span>زیاد</span>
            </div>
          </div>
        </div>
      </RvPanel>

      <!-- Top active users -->
      <RvPanel title="فعال‌ترین کاربران" subtitle="بر اساس تعامل واقعی در بازه" :icon="Trophy" :padded="false">
        <RvState v-if="!pending && !(d?.top_active_users?.length)" title="داده‌ای نیست" message="در این بازه فعالیتی ثبت نشده." />
        <div v-else class="overflow-x-auto">
          <table class="rv-table">
            <thead>
              <tr>
                <th class="w-10">#</th>
                <th>کاربر</th>
                <th class="text-center">تعامل</th>
                <th class="text-center">پخش</th>
                <th class="text-center">تکمیل</th>
                <th class="text-center">پسند</th>
                <th class="text-center">امتیاز</th>
                <th class="text-center">زمان تماشا</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in d?.top_active_users ?? []" :key="row.user_id">
                <td class="tabular-nums text-[var(--rv-faint)]">{{ fa(i + 1) }}</td>
                <td class="font-bold text-[var(--rv-text)]">{{ row.username }}</td>
                <td class="text-center tabular-nums font-black text-[var(--rv-text)]">{{ fa(row.interactions) }}</td>
                <td class="text-center tabular-nums text-[var(--rv-muted)]">{{ fa(row.plays) }}</td>
                <td class="text-center tabular-nums text-[var(--rv-muted)]">{{ fa(row.completes) }}</td>
                <td class="text-center tabular-nums text-[var(--rv-muted)]">{{ fa(row.likes) }}</td>
                <td class="text-center tabular-nums text-[var(--rv-muted)]">{{ fa(row.ratings) }}</td>
                <td class="text-center tabular-nums text-[var(--rv-muted)]">{{ (row.watch_time_hours ?? 0).toLocaleString('fa-IR') }} ساعت</td>
              </tr>
            </tbody>
          </table>
        </div>
      </RvPanel>
    </template>
  </div>
</template>

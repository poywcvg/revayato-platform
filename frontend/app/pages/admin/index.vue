<script setup lang="ts">
import type { HealthQueue } from '~/types/admin'
import type {
  AnalyticsEnvelope,
  AnalyticsOverviewData,
  AnalyticsContentData,
  AnalyticsPeriodKey,
} from '~/types/analytics'
import Users from '~icons/lucide/users-round'
import Film from '~icons/lucide/film'
import Tv from '~icons/lucide/tv'
import Eye from '~icons/lucide/eye'
import Radio from '~icons/lucide/radio'
import PlayCircle from '~icons/lucide/circle-play'
import Flame from '~icons/lucide/flame'
import Trophy from '~icons/lucide/trophy'
import Database from '~icons/lucide/database'
import RefreshCw from '~icons/lucide/refresh-cw'
import HeartPulse from '~icons/lucide/heart-pulse'
import Radar from '~icons/lucide/radar'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'داشبورد مدیریت — روایتو' })

const { api } = useApi()

const PERIODS: { key: AnalyticsPeriodKey, label: string }[] = [
  { key: '7d', label: '۷ روز' },
  { key: '30d', label: '۳۰ روز' },
  { key: '90d', label: '۹۰ روز' },
]
const period = ref<AnalyticsPeriodKey>('30d')

const { data, pending, error, refresh } = await useAsyncData(
  'admin-dashboard',
  async () => {
    const [overview, content] = await Promise.all([
      api<AnalyticsEnvelope<AnalyticsOverviewData>>('/analytics/overview/', { query: { period: period.value } }),
      api<AnalyticsEnvelope<AnalyticsContentData>>('/analytics/content/top/', { query: { period: period.value } }),
    ])
    return { overview, content }
  },
  { watch: [period] },
)

const overview = computed(() => data.value?.overview.data ?? null)
const content = computed(() => data.value?.content.data ?? null)
const stats = computed(() => content.value?.stats ?? null)
const realtime = computed(() => overview.value?.realtime ?? null)
const catalog = computed(() => overview.value?.catalog ?? null)

const KPI_ICONS: Record<string, unknown> = {
  users: Users,
  active_users: Users,
  watch_time: PlayCircle,
  plays: PlayCircle,
  views: Eye,
}
const KPI_TONES = ['accent', 'info', 'violet', 'success', 'warning'] as const
function kpiIcon(id: string) { return KPI_ICONS[id] ?? Flame }
function kpiTone(i: number) { return KPI_TONES[i % KPI_TONES.length] }

const generatedAt = computed(() => {
  const ts = data.value?.overview.generated_at
  if (!ts) return ''
  try {
    return new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit' }).format(new Date(ts))
  }
  catch { return '' }
})

const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

// ----- Open problems ------------------------------------------------------- //
// The dashboard used to show only what the site is doing well — views, watch
// time, top titles. What it could not show was whether any of it is broken, so
// a title with no playable source stayed invisible here while its viewers gave
// up. These six numbers are the counterweight, and each one is a link to the
// exact list behind it.
const { health } = useAdminOps()
const { data: healthData } = await useAsyncData(
  'admin-dashboard-health',
  () => health('source_gaps', { limit: 1 }),
  { default: () => null },
)
const HEALTH_TILES: { key: HealthQueue, label: string }[] = [
  { key: 'source_gaps', label: 'کمبود منبع' },
  { key: 'subtitle_gaps', label: 'کمبود زیرنویس' },
  { key: 'failed_checks', label: 'تست ناموفق' },
  { key: 'reports', label: 'گزارش کاربران' },
  { key: 'unverified', label: 'تأیید نشده' },
  { key: 'incomplete', label: 'ناقص' },
  { key: 'approx_ratings', label: 'نمرهٔ تقریبی' },
  { key: 'sourceless_drafts', label: 'بدون منبع' },
]
const healthCounts = computed(() => healthData.value?.counts ?? null)
const openProblems = computed(() =>
  healthCounts.value ? Object.values(healthCounts.value).reduce((a, b) => a + b, 0) : 0,
)
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">داشبورد</h1>
        <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">
          نمای کلی روایتو
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
        <div v-if="realtime?.active_watch_rooms != null" class="flex items-center gap-2.5">
          <PlayCircle class="size-4 text-[var(--rv-violet)]" />
          <span class="text-lg font-black tabular-nums text-[var(--rv-text)]">{{ fa(realtime.active_watch_rooms) }}</span>
          <span class="text-xs font-semibold text-[var(--rv-muted)]">اتاق تماشا</span>
        </div>
      </div>

      <!-- Open problems. Deliberately above the KPIs: a broken catalog is more
           urgent than a good week, and this is the only place the two meet. -->
      <RvPanel v-if="healthCounts" :icon="HeartPulse" title="مشکلات باز" :subtitle="`${fa(openProblems)} مورد نیازمند رسیدگی`">
        <template #actions>
          <NuxtLink to="/admin/operations" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs">
            <Radar class="size-3.5" />
            عملیات و خزنده‌ها
          </NuxtLink>
        </template>
        <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
          <NuxtLink
            v-for="tile in HEALTH_TILES" :key="tile.key"
            :to="{ path: '/admin/health', query: { queue: tile.key } }"
            class="rv-focus rounded-[var(--rv-radius-sm)] border border-[var(--rv-border)] bg-[var(--rv-surface-2)] p-3 text-center transition hover:border-[var(--rv-border-strong)]"
          >
            <span
              class="block text-xl font-black tabular-nums"
              :style="{ color: healthCounts[tile.key] ? 'var(--rv-danger)' : 'var(--rv-success)' }"
            >{{ fa(healthCounts[tile.key]) }}</span>
            <span class="mt-0.5 block text-xs font-bold text-[var(--rv-muted)]">{{ tile.label }}</span>
          </NuxtLink>
        </div>
      </RvPanel>

      <!-- KPI grid -->
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <template v-if="pending && !overview">
          <RvStat v-for="i in 4" :key="i" label="" :value="null" loading />
        </template>
        <RvStat
          v-for="(kpi, i) in overview?.kpis ?? []"
          v-else
          :key="kpi.id"
          :label="kpi.label"
          :value="kpi.value"
          :delta="kpi.delta_percent"
          :format="kpi.format === 'currency' ? 'number' : kpi.format"
          :hint="kpi.hint"
          :icon="kpiIcon(kpi.id)"
          :tone="kpiTone(i)"
        />
      </div>

      <!-- Content view stats -->
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <RvStat label="کل بازدیدها" :value="stats?.total_views ?? null" :icon="Eye" tone="accent" :loading="pending && !stats" hint="مجموع فیلم و سریال" />
        <RvStat label="بازدید فیلم‌ها" :value="stats?.movie_views ?? null" :icon="Film" tone="info" :loading="pending && !stats" :hint="`${fa(stats?.movie_titles_viewed)} عنوان`" />
        <RvStat label="بازدید سریال‌ها" :value="stats?.series_views ?? null" :icon="Tv" tone="violet" :loading="pending && !stats" :hint="`${fa(stats?.series_titles_viewed)} عنوان`" />
        <RvStat label="کتابخانه" :value="catalog?.total ?? null" :icon="Database" tone="success" :loading="pending && !catalog" :hint="`${fa(catalog?.movies)} فیلم · ${fa(catalog?.series)} سریال`" />
      </div>

      <!-- Most viewed lists -->
      <div class="grid gap-4 lg:grid-cols-2">
        <RvPanel title="پربازدیدترین فیلم‌ها" :icon="Trophy" :padded="false">
          <RvState v-if="!pending && !(stats?.top_movies?.length)" title="داده‌ای نیست" message="هنوز بازدیدی ثبت نشده." />
          <ol v-else class="divide-y divide-[var(--rv-border)]">
            <li v-for="(row, i) in stats?.top_movies ?? []" :key="row.id" class="flex items-center gap-3 px-4 py-2.5">
              <span class="w-5 text-center text-sm font-black tabular-nums text-[var(--rv-faint)]">{{ fa(i + 1) }}</span>
              <NuxtLink :to="`/movies/${row.slug}`" class="rv-focus min-w-0 flex-1 truncate text-sm font-bold text-[var(--rv-text)] hover:text-[var(--rv-accent)]">{{ row.title }}</NuxtLink>
              <span class="flex items-center gap-1 text-xs font-black tabular-nums text-[var(--rv-muted)]">
                <Eye class="size-3.5" />{{ fa(row.view_count) }}
              </span>
            </li>
          </ol>
        </RvPanel>

        <RvPanel title="پربازدیدترین سریال‌ها" :icon="Trophy" :padded="false">
          <RvState v-if="!pending && !(stats?.top_series?.length)" title="داده‌ای نیست" message="هنوز بازدیدی ثبت نشده." />
          <ol v-else class="divide-y divide-[var(--rv-border)]">
            <li v-for="(row, i) in stats?.top_series ?? []" :key="row.id" class="flex items-center gap-3 px-4 py-2.5">
              <span class="w-5 text-center text-sm font-black tabular-nums text-[var(--rv-faint)]">{{ fa(i + 1) }}</span>
              <NuxtLink :to="`/series/${row.slug}`" class="rv-focus min-w-0 flex-1 truncate text-sm font-bold text-[var(--rv-text)] hover:text-[var(--rv-accent)]">{{ row.title }}</NuxtLink>
              <span class="flex items-center gap-1 text-xs font-black tabular-nums text-[var(--rv-muted)]">
                <Eye class="size-3.5" />{{ fa(row.view_count) }}
              </span>
            </li>
          </ol>
        </RvPanel>
      </div>

      <!-- Most active content (tracked engagement) -->
      <RvPanel title="پرمخاطب‌ترین محتوا در بازه" subtitle="بر اساس فعالیت واقعی کاربران" :icon="Flame" :padded="false">
        <RvState v-if="!pending && !(content?.top_watched?.length)" title="داده‌ای نیست" message="در این بازه فعالیتی ثبت نشده." />
        <div v-else class="overflow-x-auto">
          <table class="rv-table">
            <thead>
              <tr>
                <th class="w-10">#</th>
                <th>عنوان</th>
                <th>نوع</th>
                <th class="text-center">فعالیت</th>
                <th class="text-center">بازدید</th>
                <th class="text-center">پخش</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in content?.top_watched ?? []" :key="`${row.content_type}-${row.id}`">
                <td class="tabular-nums text-[var(--rv-faint)]">{{ fa(i + 1) }}</td>
                <td>
                  <NuxtLink :to="`/${row.content_type === 'series' ? 'series' : 'movies'}/${row.slug}`" class="rv-focus font-bold text-[var(--rv-text)] hover:text-[var(--rv-accent)]">{{ row.title }}</NuxtLink>
                </td>
                <td>
                  <RvBadge :tone="row.content_type === 'series' ? 'violet' : 'info'">{{ row.content_type === 'series' ? 'سریال' : 'فیلم' }}</RvBadge>
                </td>
                <td class="text-center tabular-nums font-black text-[var(--rv-text)]">{{ fa(row.activity) }}</td>
                <td class="text-center tabular-nums text-[var(--rv-muted)]">{{ fa(row.view_count) }}</td>
                <td class="text-center tabular-nums text-[var(--rv-muted)]">{{ fa(row.playback_events) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </RvPanel>
    </template>
  </div>
</template>

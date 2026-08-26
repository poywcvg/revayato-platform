<script setup lang="ts">
import Activity from '~icons/lucide/activity'
import Clapperboard from '~icons/lucide/clapperboard'
import Film from '~icons/lucide/film'
import Heart from '~icons/lucide/heart'
import Info from '~icons/lucide/info'
import Refresh from '~icons/lucide/refresh-cw'
import Star from '~icons/lucide/star'
import Tv from '~icons/lucide/tv'
import Users from '~icons/lucide/users-round'
import type { Component } from 'vue'
import type { AnalyticsPeriodKey } from '~/types/analytics'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'آنالیتیکس پیشرفته', robots: 'noindex, nofollow' })

const {
  store,
  fetchOverview,
  fetchEngagement,
  fetchAdminHealth,
  refreshAll,
  setPeriod,
} = useAnalytics()

const refreshing = ref(false)
const autoRefresh = ref(true)
const polling = usePolling(
  () => {
    if (!document.hidden) {
      void fetchOverview(true)
      void fetchEngagement(true)
      void fetchAdminHealth(true)
    }
  },
  { intervalMs: 60_000, immediate: false },
)

const period = computed({
  get: () => store.period,
  set: (value: AnalyticsPeriodKey) => {
    setPeriod(value)
    void load()
  },
})

const overview = computed(() => store.overview?.payload.data || null)
const users = computed(() => store.users?.payload.data || null)
const content = computed(() => store.content?.payload.data || null)
const engagement = computed(() => store.engagement?.payload.data || null)
const generatedAt = computed(() => store.overview?.payload.generated_at || null)
const periodMeta = computed(() => store.overview?.payload.period || null)
const health = computed(() => store.health?.payload || null)

const kpiMeta: Record<string, { icon: Component, tone: 'green' | 'blue' | 'amber' | 'violet' | 'rose' | 'slate' | 'teal' }> = {
  total_users: { icon: Users, tone: 'green' },
  active_users: { icon: Activity, tone: 'teal' },
  new_signups_today: { icon: Users, tone: 'amber' },
  total_content: { icon: Film, tone: 'blue' },
  watch_hours: { icon: Clapperboard, tone: 'violet' },
  likes_total: { icon: Heart, tone: 'rose' },
}

const registrationLabels = computed(() =>
  (users.value?.registrations.points || []).map(point => formatShortDate(point.date)),
)
const registrationValues = computed(() => users.value?.registrations.points.map(point => point.value) || [])
const weekdayLabels = computed(() => users.value?.active_by_weekday.map(item => item.label) || [])
const weekdayValues = computed(() => users.value?.active_by_weekday.map(item => item.value) || [])
const deviceSlices = computed(() => users.value?.action_breakdown?.map(item => ({ label: item.label, value: item.value })) || [])
const topWatchedLabels = computed(() => (content.value?.top_watched || []).slice().reverse().map(item => truncate(item.title, 22)))
const topWatchedValues = computed(() => (content.value?.top_watched || []).slice().reverse().map(item => item.activity))
const sessionLabels = computed(() => (content.value?.sessions_over_time || []).map(point => formatShortDate(point.date)))
const sessionValues = computed(() => content.value?.sessions_over_time.map(point => point.value) || [])
const searchLabels = computed(() => (engagement.value?.search_terms || []).slice(0, 10).map(item => item.term).reverse())
const searchValues = computed(() => (engagement.value?.search_terms || []).slice(0, 10).map(item => item.count).reverse())

const activeUserRows = computed(() => (users.value?.top_active_users || []).map(row => ({
  username: row.username,
  watch_time_hours: row.watch_time_hours,
  events: row.events,
  last_seen: row.last_seen ? formatDateTime(row.last_seen) : '—',
})))

const recentRows = computed(() => (content.value?.recently_added || []).map(row => ({
  title: row.title,
  type: row.content_type === 'series' ? 'سریال' : 'فیلم',
  view_count: row.view_count,
  created_at: row.created_at ? formatDate(row.created_at) : '—',
  slug: row.slug,
  content_type: row.content_type,
})))

const anyError = computed(() =>
  store.errors.overview || store.errors.users || store.errors.content || store.errors.engagement || store.errors.health || '',
)
const loadingInitial = computed(() =>
  !overview.value
  && (store.loading.overview || store.loading.users || store.loading.content || store.loading.engagement || store.loading.health),
)

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max)}…` : value
}

function formatShortDate(value: string) {
  try {
    return new Intl.DateTimeFormat('fa-IR', { month: 'short', day: 'numeric' }).format(new Date(value))
  } catch {
    return value.slice(5)
  }
}

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium' }).format(new Date(value))
  } catch {
    return '—'
  }
}

function formatDateTime(value: string) {
  try {
    return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  } catch {
    return '—'
  }
}

function formatPeriodRange() {
  const meta = periodMeta.value
  if (!meta?.start || !meta?.end) return '—'
  try {
    const formatter = new Intl.DateTimeFormat('fa-IR', {
      dateStyle: 'medium',
      timeZone: meta.timezone,
    })
    return `${formatter.format(new Date(meta.start))} تا ${formatter.format(new Date(meta.end))}`
  } catch {
    return '—'
  }
}

async function load() {
  await refreshAll(true)
}

async function onRefresh() {
  refreshing.value = true
  try {
    await load()
  } finally {
    refreshing.value = false
  }
}

watch(autoRefresh, value => {
  if (value) polling.start()
  else polling.stop()
})
onMounted(() => {
  void load()
  if (autoRefresh.value) polling.start()
})
</script>

<template>
  <div class="admin-dashboard p-4 sm:p-6 lg:p-8" :aria-busy="loadingInitial || refreshing">
    <header class="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p class="text-xs font-black text-[var(--admin-accent)]">آنالیتیکس پیشرفته · دیتابیس زنده</p>
        <h1 class="mt-1 text-2xl font-black tracking-tight sm:text-3xl">داشبورد عملکرد روایتو</h1>
        <p class="mt-2 max-w-2xl text-sm leading-7 text-[var(--admin-muted)]">
          KPI، کاربران، محتوا، تعامل و نشست‌های واچ‌پارتی از Postgres.
          <span v-if="periodMeta" class="block text-xs">
            {{ formatPeriodRange() }}
            <span v-if="periodMeta.timezone"> · {{ periodMeta.timezone }}</span>
            <span v-if="generatedAt"> · به‌روز {{ formatDateTime(generatedAt) }}</span>
            <span v-if="autoRefresh" class="text-[var(--admin-accent)]"> · زنده هر ۶۰ ثانیه</span>
          </span>
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <label class="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[var(--admin-border)] bg-white px-3 text-xs font-bold text-[var(--admin-muted)]">
          <input v-model="autoRefresh" type="checkbox" class="size-4 accent-[var(--admin-primary)]">
          زنده
        </label>
        <AnalyticsPeriodPicker v-model="period" />
        <AdminButton variant="secondary" :loading="refreshing" :disabled="loadingInitial" @click="onRefresh">
          <template #icon><Refresh class="size-4" /></template>
          به‌روزرسانی
        </AdminButton>
      </div>
    </header>

    <AnalyticsNav />

    <AdminCard v-if="anyError && !overview" class="p-4">
      <AdminState
        kind="error"
        title="دریافت آمار ممکن نشد"
        :message="anyError"
        @retry="load()"
      />
    </AdminCard>

    <template v-else-if="loadingInitial">
      <div class="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
        <div v-for="index in 6" :key="index" class="h-40 animate-pulse rounded-[20px] bg-white/70" />
      </div>
      <div class="mt-5 h-80 animate-pulse rounded-[20px] bg-white/70" />
    </template>

    <template v-else>
      <div
        v-if="anyError"
        class="mb-4 flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs leading-6 text-amber-900"
        role="status"
      >
        <Info class="mt-0.5 size-4 shrink-0" />
        بخشی از داده‌ها تازه نشد؛ آخرین پاسخ موفق نمایش داده می‌شود.
      </div>

      <!-- Realtime -->
      <div class="mb-5 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,10.5rem),1fr))]">
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">کاربران لاگین‌شده آنلاین</p>
          <p class="mt-2 text-2xl font-black text-[var(--admin-primary)] tabular-nums">
            {{ (overview?.realtime.online_users || 0).toLocaleString('fa-IR') }}
          </p>
          <p class="mt-1 text-[10px] leading-4 text-[var(--admin-muted)]">
            heartbeat ≈ {{ (overview?.realtime.window_seconds || 90).toLocaleString('fa-IR') }}ث
            <span v-if="overview?.realtime.sources">
              · حضور {{ (overview.realtime.sources.presence || 0).toLocaleString('fa-IR') }}
              · واچ‌پارتی {{ (overview.realtime.sources.watchparty || 0).toLocaleString('fa-IR') }}
            </span>
          </p>
        </AdminCard>
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">مهمان آنلاین</p>
          <p class="mt-2 text-2xl font-black tabular-nums">
            {{ (overview?.realtime.online_guests || 0).toLocaleString('fa-IR') }}
          </p>
          <p class="mt-1 text-[10px] text-[var(--admin-muted)]">
            مجموع {{ (overview?.realtime.online_total || overview?.realtime.online_users || 0).toLocaleString('fa-IR') }}
          </p>
        </AdminCard>
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">نشست پخش زنده</p>
          <p class="mt-2 text-2xl font-black tabular-nums">
            {{ (overview?.realtime.live_watch_sessions || 0).toLocaleString('fa-IR') }}
          </p>
          <p class="mt-1 text-[10px] text-[var(--admin-muted)]">
            در حال پخش {{ (overview?.realtime.playing_sessions || 0).toLocaleString('fa-IR') }}
          </p>
        </AdminCard>
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">اتاق واچ‌پارتی زنده</p>
          <p class="mt-2 text-2xl font-black tabular-nums">
            {{ (overview?.realtime.active_watch_rooms || 0).toLocaleString('fa-IR') }}
          </p>
          <p class="mt-1 text-[10px] text-[var(--admin-muted)]">فقط اتاق‌های منقضی‌نشده با حضور تازه</p>
        </AdminCard>
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">دوبله در کاتالوگ</p>
          <p class="mt-2 text-2xl font-black tabular-nums">
            {{ (overview?.catalog.dubbed || 0).toLocaleString('fa-IR') }}
          </p>
        </AdminCard>
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">با زیرنویس فارسی</p>
          <p class="mt-2 text-2xl font-black tabular-nums">
            {{ (overview?.catalog.with_subtitle || 0).toLocaleString('fa-IR') }}
          </p>
        </AdminCard>
      </div>

      <!-- KPIs -->
      <div class="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
        <AnalyticsKpiCard
          v-for="kpi in (overview?.kpis || [])"
          :key="kpi.id"
          :label="kpi.label"
          :value="kpi.value"
          :delta-percent="kpi.delta_percent"
          :hint="kpi.hint"
          :format="kpi.format || 'number'"
          :icon="kpiMeta[kpi.id]?.icon"
          :tone="kpiMeta[kpi.id]?.tone || 'green'"
        />
      </div>

      <!-- Catalog detail cards -->
      <div class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <AdminCard class="p-4">
          <div class="flex items-center gap-3">
            <span class="grid size-10 place-items-center rounded-2xl bg-[var(--admin-surface-muted)] text-[var(--admin-primary)]">
              <Film class="size-4.5" />
            </span>
            <div>
              <p class="text-xs font-bold text-[var(--admin-muted)]">فیلم منتشرشده</p>
              <p class="text-xl font-black tabular-nums">{{ (overview?.catalog.movies || 0).toLocaleString('fa-IR') }}</p>
            </div>
          </div>
        </AdminCard>
        <AdminCard class="p-4">
          <div class="flex items-center gap-3">
            <span class="grid size-10 place-items-center rounded-2xl bg-[var(--admin-surface-muted)] text-[var(--admin-primary)]">
              <Tv class="size-4.5" />
            </span>
            <div>
              <p class="text-xs font-bold text-[var(--admin-muted)]">سریال منتشرشده</p>
              <p class="text-xl font-black tabular-nums">{{ (overview?.catalog.series || 0).toLocaleString('fa-IR') }}</p>
            </div>
          </div>
        </AdminCard>
        <AdminCard class="p-4">
          <div class="flex items-center gap-3">
            <span class="grid size-10 place-items-center rounded-2xl bg-[var(--admin-surface-muted)] text-[var(--admin-primary)]">
              <Clapperboard class="size-4.5" />
            </span>
            <div>
              <p class="text-xs font-bold text-[var(--admin-muted)]">قسمت‌ها</p>
              <p class="text-xl font-black tabular-nums">{{ (overview?.catalog.episodes || 0).toLocaleString('fa-IR') }}</p>
            </div>
          </div>
        </AdminCard>
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">رویدادهای ترکینگ</p>
          <p class="mt-2 text-xl font-black tabular-nums">{{ (overview?.database?.activity_events || 0).toLocaleString('fa-IR') }}</p>
        </AdminCard>
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">لایک / واچ‌لیست</p>
          <p class="mt-2 text-xl font-black tabular-nums">
            {{ (overview?.database?.likes || 0).toLocaleString('fa-IR') }}
            <span class="text-sm font-bold text-[var(--admin-muted)]"> / {{ (overview?.database?.watchlist || 0).toLocaleString('fa-IR') }}</span>
          </p>
        </AdminCard>
        <AdminCard class="p-4">
          <p class="text-[11px] font-bold text-[var(--admin-muted)]">امتیاز ثبت‌شده</p>
          <p class="mt-2 text-xl font-black tabular-nums">{{ (overview?.database?.ratings || 0).toLocaleString('fa-IR') }}</p>
        </AdminCard>
      </div>

      <!-- Health: catalog status + alerts + watchparty + funnel -->
      <section v-if="health" class="mt-5">
        <div class="mb-3 flex items-center justify-between gap-3">
          <h2 class="text-sm font-black text-[var(--admin-text)]">سلامت کاتالوگ و واچ‌پارتی</h2>
          <span v-if="health.health.alert_count" class="rounded-lg bg-amber-50 px-2 py-1 text-[10px] font-black text-amber-800">
            {{ (health.health.alert_count).toLocaleString('fa-IR') }} هشدار
          </span>
        </div>

        <div class="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
          <AdminCard class="p-4">
            <p class="text-[11px] font-bold text-[var(--admin-muted)]">فیلم‌ها</p>
            <p class="mt-2 text-xl font-black tabular-nums">{{ health.catalog.movies.total.toLocaleString('fa-IR') }}</p>
            <p class="mt-1 text-[10px] text-[var(--admin-muted)]">
              {{ health.catalog.movies.published.toLocaleString('fa-IR') }} منتشر · {{ health.catalog.movies.draft.toLocaleString('fa-IR') }} پیش‌نویس
            </p>
          </AdminCard>
          <AdminCard class="p-4">
            <p class="text-[11px] font-bold text-[var(--admin-muted)]">سریال‌ها</p>
            <p class="mt-2 text-xl font-black tabular-nums">{{ health.catalog.series.total.toLocaleString('fa-IR') }}</p>
            <p class="mt-1 text-[10px] text-[var(--admin-muted)]">
              {{ health.catalog.series.published.toLocaleString('fa-IR') }} منتشر · {{ health.catalog.series.draft.toLocaleString('fa-IR') }} پیش‌نویس
            </p>
          </AdminCard>
          <AdminCard class="p-4">
            <p class="text-[11px] font-bold text-[var(--admin-muted)]">قسمت‌ها</p>
            <p class="mt-2 text-xl font-black tabular-nums">{{ health.catalog.episodes.total.toLocaleString('fa-IR') }}</p>
            <p class="mt-1 text-[10px] text-[var(--admin-muted)]">
              {{ health.catalog.episodes.published.toLocaleString('fa-IR') }} منتشر
            </p>
          </AdminCard>
          <AdminCard v-if="health.watchparty.available" class="p-4">
            <p class="text-[11px] font-bold text-[var(--admin-muted)]">اتاق واچ‌پارتی</p>
            <p class="mt-2 text-xl font-black tabular-nums">{{ health.watchparty.active.toLocaleString('fa-IR') }} فعال</p>
            <p class="mt-1 text-[10px] text-[var(--admin-muted)]">
              {{ health.watchparty.total.toLocaleString('fa-IR') }} کل · {{ health.watchparty.created_in_period.toLocaleString('fa-IR') }} ساخته‌شده
            </p>
          </AdminCard>
        </div>

        <div v-if="health.health.alerts.length" class="mt-3 space-y-2">
          <NuxtLink
            v-for="alert in health.health.alerts"
            :key="alert.code"
            :to="alert.href"
            class="admin-focus flex items-center gap-3 rounded-2xl border px-3.5 py-3 text-xs font-bold"
            :class="alert.severity === 'warning'
              ? 'border-amber-200 bg-amber-50 text-amber-900'
              : 'border-[var(--admin-border)] bg-white text-[var(--admin-text)]'"
          >
            <span class="size-2 shrink-0 rounded-full" :class="alert.severity === 'warning' ? 'bg-amber-500' : 'bg-[var(--admin-muted)]'" />
            {{ alert.message }}
            <span class="ms-auto rounded-lg bg-white/70 px-2 py-0.5 text-[10px] font-black tabular-nums">{{ alert.count.toLocaleString('fa-IR') }}</span>
          </NuxtLink>
        </div>

        <div v-if="health.funnel" class="mt-3 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,10.5rem),1fr))]">
          <AdminCard class="p-4">
            <p class="text-[11px] font-bold text-[var(--admin-muted)]">بازدید → شروع پخش</p>
            <p class="mt-2 text-xl font-black tabular-nums">{{ (health.funnel.view_to_play.current ?? 0).toLocaleString('fa-IR') }}٪</p>
          </AdminCard>
          <AdminCard class="p-4">
            <p class="text-[11px] font-bold text-[var(--admin-muted)]">پخش → تکمیل</p>
            <p class="mt-2 text-xl font-black tabular-nums">{{ (health.funnel.play_to_complete.current ?? 0).toLocaleString('fa-IR') }}٪</p>
          </AdminCard>
          <AdminCard class="p-4">
            <p class="text-[11px] font-bold text-[var(--admin-muted)]">بازدید → تکمیل</p>
            <p class="mt-2 text-xl font-black tabular-nums">{{ (health.funnel.view_to_complete.current ?? 0).toLocaleString('fa-IR') }}٪</p>
          </AdminCard>
        </div>
      </section>

      <div class="mt-5 grid gap-4 xl:grid-cols-3">
        <div class="xl:col-span-2">
          <AnalyticsLineChart
            title="نشست‌های تماشا در طول زمان"
            subtitle="اتاق واچ‌پارتی + رویدادهای پخش"
            :labels="sessionLabels"
            :values="sessionValues"
            :loading="store.loading.content && !content"
          />
        </div>
        <AnalyticsDonutChart
          title="تفکیک نوع رویداد"
          subtitle="ترکیب فعالیت‌های ثبت‌شده کاربران"
          :slices="deviceSlices"
          :loading="store.loading.users && !users"
        />
      </div>

      <div class="mt-5 grid gap-4 xl:grid-cols-2">
        <AnalyticsBarChart
          title="۱۰ عنوان پربازدید"
          subtitle="رتبه‌بندی از واچ‌پارتی و شمارنده‌های واقعی"
          horizontal
          :labels="topWatchedLabels"
          :values="topWatchedValues"
          :loading="store.loading.content && !content"
        />
        <AnalyticsBarChart
          title="جستجوهای پرتکرار"
          subtitle="عبارت‌های ثبت‌شده در بازه"
          horizontal
          color="#2563eb"
          :labels="searchLabels"
          :values="searchValues"
          :loading="store.loading.engagement && !engagement"
        />
      </div>

      <div class="mt-5 grid gap-4 xl:grid-cols-2">
        <AnalyticsLineChart
          title="عضویت‌های جدید"
          subtitle="بر اساس date_joined کاربران"
          :labels="registrationLabels"
          :values="registrationValues"
          :loading="store.loading.users && !users"
        />
        <AnalyticsBarChart
          title="کاربران فعال در روزهای هفته"
          subtitle="بر اساس last_login"
          :labels="weekdayLabels"
          :values="weekdayValues"
          :loading="store.loading.users && !users"
        />
      </div>

      <div class="mt-5 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
        <AnalyticsKpiCard
          label="میانگین مدت نشست"
          :value="engagement?.average_session_minutes ?? null"
          format="raw"
          hint="دقیقه · از playback واچ‌پارتی"
          :icon="Clapperboard"
          tone="violet"
          :loading="store.loading.engagement && !engagement"
        />
        <AnalyticsKpiCard
          label="نرخ تکمیل"
          :value="engagement?.completion_rate ?? null"
          format="percent"
          hint="complete / play"
          :icon="Activity"
          tone="teal"
          :loading="store.loading.engagement && !engagement"
        />
        <AnalyticsKpiCard
          label="اتاق واچ‌پارتی"
          :value="engagement?.watch_rooms ?? null"
          hint="ایجادشده در بازه"
          :icon="Users"
          tone="blue"
          :loading="store.loading.engagement && !engagement"
        />
        <AnalyticsKpiCard
          label="لایک‌ها"
          :value="engagement?.likes_total ?? null"
          :hint="`${(engagement?.likes_in_period || 0).toLocaleString('fa-IR')} در بازه`"
          :icon="Heart"
          tone="rose"
          :loading="store.loading.engagement && !engagement"
        />
        <AnalyticsKpiCard
          label="میانگین امتیاز"
          :value="engagement?.average_rating ?? null"
          format="raw"
          :hint="`${(engagement?.ratings_total || 0).toLocaleString('fa-IR')} امتیاز`"
          :icon="Star"
          tone="amber"
          :loading="store.loading.engagement && !engagement"
        />
      </div>

      <div class="mt-5">
        <AnalyticsHeatmapChart
          title="نقشه حرارتی فعالیت"
          subtitle="ساعت × روز هفته · واچ‌پارتی، لاگین و رویدادها"
          :weekdays="content?.heatmap.weekdays || []"
          :hours="content?.heatmap.hours || []"
          :cells="content?.heatmap.cells || []"
          :loading="store.loading.content && !content"
        />
      </div>

      <div class="mt-5 grid gap-4 xl:grid-cols-2">
        <AnalyticsDataTable
          title="۱۰ کاربر فعال"
          subtitle="ترکیب لاگین، رویداد و میزبانی واچ‌پارتی"
          export-name="analytics-top-users"
          :loading="store.loading.users && !users"
          :columns="[
            { key: 'username', label: 'نام کاربری' },
            { key: 'watch_time_hours', label: 'ساعت تماشا', align: 'end' },
            { key: 'events', label: 'امتیاز فعالیت', align: 'end' },
            { key: 'last_seen', label: 'آخرین بازدید' },
          ]"
          :rows="activeUserRows"
        />
        <AnalyticsDataTable
          title="محتوای تازه‌اضافه‌شده"
          subtitle="آخرین فیلم/سریال منتشرشده"
          export-name="analytics-recent-content"
          :loading="store.loading.content && !content"
          :columns="[
            { key: 'title', label: 'عنوان' },
            { key: 'type', label: 'نوع' },
            { key: 'view_count', label: 'بازدید', align: 'end' },
            { key: 'created_at', label: 'تاریخ' },
          ]"
          :rows="recentRows"
        >
          <template #cell-title="{ row }">
            <NuxtLink
              v-if="row.slug"
              :to="row.content_type === 'series' ? `/series/${row.slug}` : `/movies/${row.slug}`"
              class="font-black text-[var(--admin-primary)] hover:underline"
              target="_blank"
            >
              {{ row.title }}
            </NuxtLink>
            <span v-else>{{ row.title }}</span>
          </template>
        </AnalyticsDataTable>
      </div>
    </template>
  </div>
</template>

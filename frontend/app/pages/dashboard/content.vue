<script setup lang="ts">
import Refresh from '~icons/lucide/refresh-cw'
import type { AnalyticsPeriodKey } from '~/types/analytics'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'آنالیتیکس محتوا', robots: 'noindex, nofollow' })

const { store, fetchContent, fetchEngagement, setPeriod } = useAnalytics()
const refreshing = ref(false)

const period = computed({
  get: () => store.period,
  set: async (value: AnalyticsPeriodKey) => {
    setPeriod(value)
    await Promise.all([fetchContent(true), fetchEngagement(true)])
  },
})

const content = computed(() => store.content?.payload.data || null)
const engagement = computed(() => store.engagement?.payload.data || null)

async function onRefresh() {
  refreshing.value = true
  try {
    await Promise.all([fetchContent(true), fetchEngagement(true)])
  } finally {
    refreshing.value = false
  }
}

function formatShortDate(value: string) {
  try {
    return new Intl.DateTimeFormat('fa-IR', { month: 'short', day: 'numeric' }).format(new Date(value))
  } catch {
    return value.slice(5)
  }
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max)}…` : value
}

onMounted(() => {
  void fetchContent(true)
  void fetchEngagement(true)
})
</script>

<template>
  <div class="admin-dashboard p-4 sm:p-6 lg:p-8">
    <header class="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p class="text-xs font-black text-[var(--admin-accent)]">بخش محتوا و تعامل</p>
        <h1 class="mt-1 text-2xl font-black tracking-tight sm:text-3xl">آنالیتیکس محتوا</h1>
        <p class="mt-2 text-sm text-[var(--admin-muted)]">
          پربازدیدها، نشست‌ها، نقشه حرارتی و جستجو.
          <span v-if="content?.catalog" class="block text-xs">
            {{ content.catalog.movies_published.toLocaleString('fa-IR') }} فیلم ·
            {{ content.catalog.series_published.toLocaleString('fa-IR') }} سریال ·
            {{ content.catalog.episodes_published.toLocaleString('fa-IR') }} قسمت
          </span>
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <AnalyticsPeriodPicker v-model="period" />
        <AdminButton variant="secondary" :loading="refreshing" @click="onRefresh">
          <template #icon><Refresh class="size-4" /></template>
          به‌روزرسانی
        </AdminButton>
      </div>
    </header>

    <AnalyticsNav />

    <div class="mb-5 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
      <AnalyticsKpiCard
        label="اتاق واچ‌پارتی"
        :value="engagement?.watch_rooms ?? null"
        hint="در بازه انتخاب‌شده"
        tone="blue"
        :loading="store.loading.engagement && !engagement"
      />
      <AnalyticsKpiCard
        label="میانگین نشست"
        :value="engagement?.average_session_minutes ?? null"
        format="raw"
        hint="دقیقه"
        tone="violet"
        :loading="store.loading.engagement && !engagement"
      />
      <AnalyticsKpiCard
        label="نرخ تکمیل"
        :value="engagement?.completion_rate ?? null"
        format="percent"
        tone="teal"
        :loading="store.loading.engagement && !engagement"
      />
      <AnalyticsKpiCard
        label="لایک / امتیاز"
        :value="engagement?.likes_total ?? null"
        :hint="`${(engagement?.ratings_total || 0).toLocaleString('fa-IR')} امتیاز`"
        tone="rose"
        :loading="store.loading.engagement && !engagement"
      />
    </div>

    <div class="grid gap-4 xl:grid-cols-2">
      <LazyAnalyticsBarChart
        title="۱۰ عنوان پربازدید"
        subtitle="رتبه از واچ‌پارتی و شمارنده‌ها"
        horizontal
        :labels="(content?.top_watched || []).slice().reverse().map(i => truncate(i.title, 24))"
        :values="(content?.top_watched || []).slice().reverse().map(i => i.activity)"
        :loading="store.loading.content && !content"
      />
      <LazyAnalyticsLineChart
        title="نشست‌های تماشا"
        subtitle="اتاق‌های ساخته‌شده + رویداد پخش"
        :labels="(content?.sessions_over_time || []).map(p => formatShortDate(p.date))"
        :values="(content?.sessions_over_time || []).map(p => p.value)"
        :loading="store.loading.content && !content"
      />
    </div>

    <div class="mt-5">
      <LazyAnalyticsHeatmapChart
        title="فعالیت تماشا (ساعت × روز هفته)"
        subtitle="واچ‌پارتی، لاگین و رویدادهای ترکینگ"
        :weekdays="content?.heatmap.weekdays || []"
        :hours="content?.heatmap.hours || []"
        :cells="content?.heatmap.cells || []"
        :loading="store.loading.content && !content"
      />
    </div>

    <div class="mt-5">
      <LazyAnalyticsBarChart
        title="عبارات جستجو"
        subtitle="Top جستجوهای ثبت‌شده"
        horizontal
        color="#7c3aed"
        :labels="(engagement?.search_terms || []).slice(0, 12).map(i => i.term).reverse()"
        :values="(engagement?.search_terms || []).slice(0, 12).map(i => i.count).reverse()"
        :loading="store.loading.engagement && !engagement"
      />
    </div>

    <div class="mt-5">
      <AnalyticsDataTable
        title="محتوای تازه + نرخ تکمیل"
        subtitle="آخرین عنوان‌ها با وضعیت تعامل"
        export-name="analytics-content-detail"
        :loading="(store.loading.content || store.loading.engagement) && !content"
        :columns="[
          { key: 'title', label: 'عنوان' },
          { key: 'type', label: 'نوع' },
          { key: 'activity', label: 'فعالیت', align: 'end' },
          { key: 'views', label: 'بازدید', align: 'end' },
          { key: 'completion', label: 'تکمیل ٪', align: 'end' },
        ]"
        :rows="(content?.recently_added || []).map((row) => {
          const top = content?.top_watched.find(item => item.id === row.id && item.content_type === row.content_type)
          const completion = engagement?.completion_by_content.find(item => item.id === row.id && item.content_type === row.content_type)
          return {
            title: row.title,
            type: row.content_type === 'series' ? 'سریال' : 'فیلم',
            activity: top?.activity ?? 0,
            views: row.view_count,
            completion: completion?.completion_rate ?? '—',
            slug: row.slug,
            content_type: row.content_type,
          }
        })"
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
  </div>
</template>

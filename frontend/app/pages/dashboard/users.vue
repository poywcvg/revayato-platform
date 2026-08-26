<script setup lang="ts">
import Refresh from '~icons/lucide/refresh-cw'
import type { AnalyticsPeriodKey } from '~/types/analytics'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'آنالیتیکس کاربران', robots: 'noindex, nofollow' })

const { store, fetchUsers, setPeriod } = useAnalytics()
const refreshing = ref(false)

const period = computed({
  get: () => store.period,
  set: async (value: AnalyticsPeriodKey) => {
    setPeriod(value)
    await fetchUsers(true)
  },
})

const granularityOptions = [
  { value: 'daily' as const, label: 'روزانه' },
  { value: 'weekly' as const, label: 'هفتگی' },
  { value: 'monthly' as const, label: 'ماهانه' },
]

const granularityLabels = { daily: 'روزانه', weekly: 'هفتگی', monthly: 'ماهانه' } as const

const periodRangeLabel = computed(() => {
  const labels: Record<AnalyticsPeriodKey, string> = {
    '7d': '۷ روز اخیر',
    '30d': '۳۰ روز اخیر',
    '90d': '۹۰ روز اخیر',
  }
  return labels[store.period]
})

const data = computed(() => store.users?.payload.data || null)

async function setGranularity(value: 'daily' | 'weekly' | 'monthly') {
  if (store.granularity === value) return
  store.setGranularity(value)
  await fetchUsers(true)
}

async function onRefresh() {
  refreshing.value = true
  try {
    await fetchUsers(true)
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

onMounted(() => { void fetchUsers(true) })
</script>

<template>
  <div class="admin-dashboard p-4 sm:p-6 lg:p-8">
    <header class="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p class="text-xs font-black text-[var(--admin-accent)]">بخش کاربران</p>
        <h1 class="mt-1 text-2xl font-black tracking-tight sm:text-3xl">آنالیتیکس کاربران</h1>
        <p class="mt-2 text-sm text-[var(--admin-muted)]">
          عضویت، فعالیت هفتگی، ترکیب رویدادها و کاربران پرتلاش — مستقیم از دیتابیس.
          <span v-if="data?.totals" class="block text-xs">
            کل {{ data.totals.users.toLocaleString('fa-IR') }} کاربر ·
            {{ data.totals.new_in_period.toLocaleString('fa-IR') }} عضویت در بازه ·
            {{ data.totals.active_in_period.toLocaleString('fa-IR') }} فعال
          </span>
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <AnalyticsPeriodPicker v-model="period" />
        <div class="inline-flex gap-1 rounded-2xl border border-[var(--admin-border)] bg-white p-1 shadow-[var(--admin-shadow)]">
          <button
            v-for="option in granularityOptions"
            :key="option.value"
            type="button"
            class="admin-focus min-h-11 rounded-xl px-3 text-xs font-black"
            :class="store.granularity === option.value
              ? 'bg-[var(--admin-primary)] text-white'
              : 'text-[var(--admin-muted)] hover:bg-[var(--admin-surface-muted)]'"
            @click="setGranularity(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
        <AdminButton variant="secondary" :loading="refreshing" @click="onRefresh">
          <template #icon><Refresh class="size-4" /></template>
          به‌روزرسانی
        </AdminButton>
      </div>
    </header>

    <AnalyticsNav />

    <AdminCard v-if="store.errors.users && !data" class="p-4">
      <AdminState kind="error" title="خطا در دریافت کاربران" :message="store.errors.users" @retry="fetchUsers(true)" />
    </AdminCard>

    <template v-else>
      <div class="grid gap-4 xl:grid-cols-3">
        <div class="xl:col-span-2">
          <AnalyticsLineChart
            title="ثبت‌نام‌های جدید"
            :subtitle="`بازه ${periodRangeLabel} · تفکیک ${granularityLabels[store.granularity]}`"
            :labels="(data?.registrations.points || []).map(p => formatShortDate(p.date))"
            :values="(data?.registrations.points || []).map(p => p.value)"
            :loading="store.loading.users && !data"
          />
        </div>
        <AnalyticsDonutChart
          title="تفکیک نوع رویداد"
          subtitle="ترکیب فعالیت‌های ثبت‌شده در بازه"
          :slices="(data?.action_breakdown || []).map(d => ({ label: d.label, value: d.value }))"
          :loading="store.loading.users && !data"
        />
      </div>

      <div class="mt-5">
        <AnalyticsBarChart
          title="کاربران فعال بر اساس روز هفته"
          subtitle="از last_login کاربران"
          :labels="(data?.active_by_weekday || []).map(i => i.label)"
          :values="(data?.active_by_weekday || []).map(i => i.value)"
          :loading="store.loading.users && !data"
        />
      </div>

      <div class="mt-5">
        <AnalyticsDataTable
          title="۱۰ کاربر فعال"
          subtitle="ترکیب لاگین، رویداد و میزبانی واچ‌پارتی"
          export-name="analytics-users-top"
          :loading="store.loading.users && !data"
          :columns="[
            { key: 'username', label: 'نام کاربری' },
            { key: 'watch_time_hours', label: 'ساعت تماشا', align: 'end' },
            { key: 'events', label: 'امتیاز فعالیت', align: 'end' },
            { key: 'last_seen', label: 'آخرین بازدید' },
          ]"
          :rows="(data?.top_active_users || []).map(row => ({
            username: row.username,
            watch_time_hours: row.watch_time_hours,
            events: row.events,
            last_seen: row.last_seen ? new Date(row.last_seen).toLocaleString('fa-IR') : '—',
          }))"
        />
      </div>
    </template>
  </div>
</template>

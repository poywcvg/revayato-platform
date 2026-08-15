<script setup lang="ts">
import AlertTriangle from '~icons/lucide/triangle-alert'
import CalendarDays from '~icons/lucide/calendar-days'
import Check from '~icons/lucide/check'
import Database from '~icons/lucide/database'
import Play from '~icons/lucide/play'
import Refresh from '~icons/lucide/rotate-cw'
import Save from '~icons/lucide/save'
import Settings from '~icons/lucide/settings-2'
import ShieldCheck from '~icons/lucide/shield-check'
import Square from '~icons/lucide/square'
import TrendingUp from '~icons/lucide/trending-up'
import type { AppErrorDetails, CatalogImporterSettings, CatalogSyncMode, CatalogSyncRun } from '~/types'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'ورود خودکار کاتالوگ', robots: 'noindex, nofollow' })

const adminApi = useAdminMovies()
const notifications = useNotifications()
const runs = ref<CatalogSyncRun[]>([])
const selectedMode = ref<CatalogSyncMode>('daily')
const importer = ref<CatalogImporterSettings | null>(null)
const loading = ref(true)
const actionLoading = ref(false)
const settingsLoading = ref(false)
const error = ref<AppErrorDetails | null>(null)
const runsPolling = usePolling(() => void loadRuns(true), { intervalMs: 2500, immediate: false })

const activeRun = computed(() => runs.value.find(run => run.is_active) || null)
const statusLabels: Record<CatalogSyncRun['status'], string> = {
  queued: 'در صف', running: 'در حال اجرا', cancelling: 'در حال لغو', cancelled: 'لغوشده',
  succeeded: 'کامل‌شده', failed: 'ناموفق',
}
const phaseLabels: Record<string, string> = {
  queued: 'در انتظار worker', discovering: 'در حال دریافت شناسه‌ها', importing: 'در حال دریافت و ذخیره متادیتا',
  discovery_retry: 'تلاش مجدد برای دریافت فهرست', import_retry: 'تلاش مجدد برای ورود',
  cancelling: 'در حال توقف امن', cancelled: 'لغوشده', complete: 'کامل', failed: 'متوقف‌شده با خطا',
}
const modeLabels: Record<CatalogSyncMode, string> = {
  daily: 'فیلم‌های جدید روز', trending: 'ترندها', incremental: 'افزایشی قدیمی', full: 'کامل',
}

function formatNumber(value: number) {
  return value.toLocaleString('fa-IR')
}

async function loadRuns(silent = false) {
  if (!silent) loading.value = true
  try {
    const response = await adminApi.catalogSyncRuns(12)
    runs.value = response.results
    error.value = null
  } catch (cause) {
    if (!silent) error.value = getAppError(cause, 'وضعیت ورود خودکار دریافت نشد.')
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadImporterSettings() {
  try {
    importer.value = await adminApi.importerSettings()
  } catch (cause) {
    error.value = getAppError(cause, 'تنظیمات ایمپورتر دریافت نشد.')
  }
}

async function saveImporterSettings() {
  if (!importer.value) return
  settingsLoading.value = true
  try {
    importer.value = await adminApi.updateImporterSettings({
      language: importer.value.language,
      fallback_language: importer.value.fallback_language,
      region: importer.value.region,
      daily_lookback_days: importer.value.daily_lookback_days,
      daily_lookahead_days: importer.value.daily_lookahead_days,
      daily_max_pages: importer.value.daily_max_pages,
      trending_window: importer.value.trending_window,
      trending_max_pages: importer.value.trending_max_pages,
      import_people_images: importer.value.import_people_images,
      cast_import_limit: importer.value.cast_import_limit,
      fetch_imdb_ratings: importer.value.fetch_imdb_ratings,
      feature_trending: importer.value.feature_trending,
      auto_publish: importer.value.auto_publish,
      automation_enabled: importer.value.automation_enabled,
      automation_mode: importer.value.automation_mode,
      automation_interval_hours: importer.value.automation_interval_hours,
    })
    notifications.success('تنظیمات ذخیره شد', 'اجرای بعدی ایمپورتر از این تنظیمات استفاده می‌کند.')
  } catch (cause) {
    notifications.notifyError(cause, 'تنظیمات ذخیره نشد')
  } finally {
    settingsLoading.value = false
  }
}

async function startSync() {
  actionLoading.value = true
  try {
    const run = await adminApi.startCatalogSync(selectedMode.value)
    runs.value = [run, ...runs.value.filter(item => item.id !== run.id)]
    const message = selectedMode.value === 'full'
      ? 'فهرست کامل TMDB در حال آماده‌سازی است.'
      : selectedMode.value === 'trending'
        ? 'ترندهای روز یا هفته در حال دریافت و ورود هستند.'
        : 'فیلم‌های تازه اکران‌شده امروز در حال دریافت و ورود هستند.'
    notifications.success('فرآیند شروع شد', message)
  } catch (cause) {
    const details = notifications.notifyError(cause, 'شروع فرآیند ممکن نشد.')
    error.value = details
    await loadRuns(true)
  } finally {
    actionLoading.value = false
  }
}

async function cancelSync() {
  if (!activeRun.value) return
  actionLoading.value = true
  try {
    const run = await adminApi.cancelCatalogSync(activeRun.value.id)
    runs.value = runs.value.map(item => item.id === run.id ? run : item)
    notifications.success('درخواست لغو ثبت شد', 'پردازش پس از پایان آیتم فعلی متوقف می‌شود.')
  } catch (cause) {
    notifications.notifyError(cause, 'لغو انجام نشد')
  } finally {
    actionLoading.value = false
  }
}

await Promise.all([loadRuns(), loadImporterSettings()])
onMounted(() => { runsPolling.start() })
</script>

<template>
  <div class="px-4 py-6 sm:px-6 lg:px-8 lg:py-9">
    <header class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div class="min-w-0">
        <div class="mb-2 flex flex-wrap items-center gap-2 text-xs font-bold text-[var(--admin-muted)]">
          <span>استودیو روایتو</span><span>/</span><span class="text-[var(--admin-primary)]">اتوماسیون TMDB</span>
        </div>
        <h1 class="text-2xl font-black tracking-tight sm:text-3xl">ورود کاملاً خودکار فیلم‌ها</h1>
        <p class="mt-2 max-w-3xl text-sm leading-7 text-[var(--admin-muted)]">
          با یک دکمه، شناسه‌های رسمی TMDB دریافت و همه متادیتا به‌صورت ایمن و قابل ادامه ذخیره می‌شود.
        </p>
      </div>
      <AdminButton class="w-full shrink-0 sm:w-auto" variant="secondary" :disabled="loading" @click="loadRuns()">
        <template #icon><Refresh class="size-4" :class="loading && 'animate-spin'" /></template>
        به‌روزرسانی وضعیت
      </AdminButton>
    </header>

    <AdminState v-if="error && !loading" class="mt-6" kind="error" title="وضعیت سیستم در دسترس نیست" :message="error.message" @retry="loadRuns()" />

    <AdminCard v-if="activeRun" class="mt-7 overflow-hidden">
      <div class="border-b border-[var(--admin-border)] bg-teal-50/70 p-5 sm:p-7">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div class="grid size-12 shrink-0 place-items-center rounded-2xl bg-[var(--admin-primary)] text-white"><Database class="size-5" /></div>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2"><h2 class="font-black">اجرای شماره {{ activeRun.id.toLocaleString('fa-IR') }}</h2><AdminBadge :tone="activeRun.status">{{ statusLabels[activeRun.status] }}</AdminBadge></div>
            <p class="mt-1 text-xs text-[var(--admin-muted)]">{{ modeLabels[activeRun.mode] }} · {{ phaseLabels[activeRun.phase] || activeRun.phase }}</p>
          </div>
          <AdminButton v-if="activeRun.can_cancel" variant="danger" :loading="actionLoading" @click="cancelSync"><template #icon><Square class="size-3.5 fill-current" /></template>لغو فرآیند</AdminButton>
        </div>

        <div class="mt-6">
          <div class="mb-2 flex items-center justify-between text-xs font-bold"><span>{{ formatNumber(activeRun.processed_count) }} از {{ activeRun.total_count ? formatNumber(activeRun.total_count) : '—' }}</span><span dir="ltr">{{ activeRun.progress_percent.toLocaleString('fa-IR') }}%</span></div>
          <div class="h-3 overflow-hidden rounded-full bg-white shadow-inner"><div class="h-full rounded-full bg-gradient-to-l from-emerald-500 to-sky-600 transition-[width] duration-500" :style="{ width: `${Math.min(100, activeRun.progress_percent)}%` }" /></div>
          <p v-if="activeRun.phase === 'discovering'" class="mt-2 text-xs text-[var(--admin-muted)]">تا این لحظه {{ formatNumber(activeRun.discovered_count) }} شناسه آماده شده؛ درصد پس از تکمیل فهرست نمایش داده می‌شود.
          </p>
        </div>

        <div class="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
          <div class="rounded-xl bg-white p-3"><p class="text-[11px] text-[var(--admin-muted)]">ساخته‌شده</p><p class="mt-1 font-latin text-lg font-black text-emerald-700">{{ formatNumber(activeRun.created_count) }}</p></div>
          <div class="rounded-xl bg-white p-3"><p class="text-[11px] text-[var(--admin-muted)]">به‌روزشده</p><p class="mt-1 font-latin text-lg font-black text-teal-800">{{ formatNumber(activeRun.updated_count) }}</p></div>
          <div class="rounded-xl bg-white p-3"><p class="text-[11px] text-[var(--admin-muted)]">منتشرشده</p><p class="mt-1 font-latin text-lg font-black">{{ formatNumber(activeRun.published_count) }}</p></div>
          <div class="rounded-xl bg-white p-3"><p class="text-[11px] text-[var(--admin-muted)]">ردشده</p><p class="mt-1 font-latin text-lg font-black text-amber-700">{{ formatNumber(activeRun.skipped_count) }}</p></div>
          <div class="rounded-xl bg-white p-3"><p class="text-[11px] text-[var(--admin-muted)]">خطا</p><p class="mt-1 font-latin text-lg font-black text-red-700">{{ formatNumber(activeRun.error_count) }}</p></div>
        </div>
      </div>
    </AdminCard>

    <div v-else class="mt-7 grid gap-5 lg:grid-cols-[1.2fr_.8fr]">
      <AdminCard class="p-5 sm:p-7">
        <div class="flex items-start gap-3"><div class="grid size-11 shrink-0 place-items-center rounded-2xl bg-[var(--admin-surface-muted)] text-[var(--admin-primary)]"><Database class="size-5" /></div><div><h2 class="text-lg font-black">نوع فرآیند را انتخاب کنید</h2><p class="mt-1 text-xs leading-6 text-[var(--admin-muted)]">هر دو حالت بدون نیاز به حضور انسان ادامه پیدا می‌کنند.</p></div></div>
        <div class="mt-6 grid gap-3 sm:grid-cols-3">
          <button class="admin-focus rounded-2xl border p-5 text-right" :class="selectedMode === 'daily' ? 'border-[var(--admin-primary)] bg-teal-50 ring-2 ring-[var(--admin-primary)]/10' : 'border-[var(--admin-border)] bg-white'" @click="selectedMode = 'daily'">
            <span class="flex items-center justify-between"><span class="flex items-center gap-2"><CalendarDays class="size-4 text-teal-800" /><strong>جدیدهای روز</strong></span><Check v-if="selectedMode === 'daily'" class="size-5 text-emerald-600" /></span>
            <span class="mt-2 block text-xs leading-6 text-[var(--admin-muted)]">اکران‌های امروز، Now Playing و عنوان‌های تازه تغییرکرده را وارد می‌کند.</span>
          </button>
          <button class="admin-focus rounded-2xl border p-5 text-right" :class="selectedMode === 'trending' ? 'border-[var(--admin-primary)] bg-teal-50 ring-2 ring-[var(--admin-primary)]/10' : 'border-[var(--admin-border)] bg-white'" @click="selectedMode = 'trending'">
            <span class="flex items-center justify-between"><span class="flex items-center gap-2"><TrendingUp class="size-4 text-rose-700" /><strong>ترندها</strong></span><Check v-if="selectedMode === 'trending'" class="size-5 text-emerald-600" /></span>
            <span class="mt-2 block text-xs leading-6 text-[var(--admin-muted)]">فیلم‌های ترند TMDB را می‌گیرد و برای ریل ترند و اسلایدر علامت‌گذاری می‌کند.</span>
          </button>
          <button class="admin-focus rounded-2xl border p-5 text-right" :class="selectedMode === 'full' ? 'border-[var(--admin-primary)] bg-teal-50 ring-2 ring-[var(--admin-primary)]/10' : 'border-[var(--admin-border)] bg-white'" @click="selectedMode = 'full'">
            <span class="flex items-center justify-between"><strong>ورود کامل اولیه</strong><Check v-if="selectedMode === 'full'" class="size-5 text-emerald-600" /></span>
            <span class="mt-2 block text-xs leading-6 text-[var(--admin-muted)]">همه شناسه‌های غیربزرگسال خروجی رسمی TMDB؛ مناسب راه‌اندازی نخست.</span>
          </button>
        </div>
        <div v-if="selectedMode === 'full'" class="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs leading-6 text-amber-900"><div class="flex gap-2"><AlertTriangle class="mt-0.5 size-4 shrink-0" /><p><strong class="block">ورود کامل ممکن است ساعت‌ها یا روزها زمان ببرد.</strong>فرآیند قابل لغو، idempotent و محدودشده است تا به API فشار نیاید.</p></div></div>
        <AdminButton class="mt-5 w-full sm:w-auto" :loading="actionLoading" @click="startSync"><template #icon><Play class="size-4 fill-current" /></template>شروع ورود {{ modeLabels[selectedMode] }}</AdminButton>
      </AdminCard>

      <AdminCard class="p-5 sm:p-7">
        <div class="flex items-center gap-3"><ShieldCheck class="size-6 text-emerald-700" /><h2 class="text-lg font-black">چطور کار می‌کند</h2></div>
        <ul class="mt-5 space-y-4 text-xs leading-6 text-[var(--admin-muted)]">
          <li class="flex gap-2"><Check class="mt-1 size-4 shrink-0 text-emerald-600" />کلید TMDB فقط روی سرور می‌ماند و به مرورگر ارسال نمی‌شود.</li>
          <li class="flex gap-2"><Check class="mt-1 size-4 shrink-0 text-emerald-600" />شناسه TMDB از ساخت فیلم تکراری جلوگیری می‌کند.</li>
          <li class="flex gap-2"><Check class="mt-1 size-4 shrink-0 text-emerald-600" />متادیتا ابتدا پیش‌نویس ذخیره می‌شود؛ فایل ویدئو از TMDB دانلود نمی‌شود.</li>
          <li class="flex gap-2"><Check class="mt-1 size-4 shrink-0 text-emerald-600" />بعد از ورود، از پنل فیلم‌ها می‌توانید هر عنوان را فوری منتشر کنید.</li>
        </ul>
      </AdminCard>
    </div>

    <AdminCard v-if="importer" class="mt-6 p-5 sm:p-7">
      <div class="flex flex-col gap-4 border-b border-[var(--admin-border)] pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex items-start gap-3"><div class="grid size-11 shrink-0 place-items-center rounded-2xl bg-[var(--admin-surface-muted)] text-[var(--admin-primary)]"><Settings class="size-5" /></div><div><h2 class="text-lg font-black">تنظیمات ایمپورتر</h2><p class="mt-1 text-xs leading-6 text-[var(--admin-muted)]">زبان، دامنه ورود، عکس عوامل، امتیاز IMDb و اجرای زمان‌بندی‌شده را از همین‌جا تغییر دهید.</p></div></div>
        <AdminButton :loading="settingsLoading" @click="saveImporterSettings"><template #icon><Save class="size-4" /></template>ذخیره تنظیمات</AdminButton>
      </div>

      <div class="mt-6 grid gap-5 lg:grid-cols-3">
        <section class="rounded-2xl bg-[var(--admin-surface-muted)]/55 p-4">
          <h3 class="text-sm font-black">زبان و محدوده</h3>
          <div class="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <AdminField label="زبان اصلی TMDB"><input v-model.trim="importer.language" dir="ltr" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm" placeholder="fa-IR" ></AdminField>
            <AdminField label="زبان جایگزین"><input v-model.trim="importer.fallback_language" dir="ltr" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm" placeholder="en-US" ></AdminField>
            <AdminField label="منطقه"><input v-model.trim="importer.region" dir="ltr" maxlength="2" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm uppercase" placeholder="IR" ></AdminField>
          </div>
        </section>

        <section class="rounded-2xl bg-[var(--admin-surface-muted)]/55 p-4">
          <h3 class="text-sm font-black">جدیدهای روز و ترند</h3>
          <div class="mt-4 grid grid-cols-2 gap-3">
            <AdminField label="روزهای قبل"><input v-model.number="importer.daily_lookback_days" type="number" min="1" max="14" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm" ></AdminField>
            <AdminField label="روزهای آینده"><input v-model.number="importer.daily_lookahead_days" type="number" min="0" max="90" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm" ></AdminField>
            <AdminField label="صفحه‌های روزانه"><input v-model.number="importer.daily_max_pages" type="number" min="1" max="100" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm" ></AdminField>
            <AdminField label="صفحه‌های ترند"><input v-model.number="importer.trending_max_pages" type="number" min="1" max="20" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm" ></AdminField>
            <AdminField class="col-span-2" label="بازه ترند"><select v-model="importer.trending_window" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 text-sm"><option value="day">امروز</option><option value="week">این هفته</option></select></AdminField>
          </div>
        </section>

        <section class="rounded-2xl bg-[var(--admin-surface-muted)]/55 p-4">
          <h3 class="text-sm font-black">متادیتا و انتشار</h3>
          <div class="mt-4 space-y-3 text-xs font-bold">
            <AdminField label="تعداد بازیگران در هر عنوان">
              <input
                v-model.number="importer.cast_import_limit"
                type="number"
                min="1"
                max="50"
                class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm"
              >
            </AdminField>
            <p class="rounded-xl border border-[var(--admin-border)] bg-white p-3 font-normal leading-6 text-[var(--admin-muted)]">
              بین ۱ تا ۵۰ نفر از لیست Cast تی‌ام‌دی‌بی برای هر فیلم یا سریال ذخیره می‌شود.
            </p>
            <label class="flex cursor-pointer items-center justify-between gap-3 rounded-xl bg-white p-3"><span>دانلود عکس بازیگران و کارگردان</span><input v-model="importer.import_people_images" type="checkbox" class="size-4 accent-[var(--admin-primary)]" ></label>
            <label class="flex cursor-pointer items-center justify-between gap-3 rounded-xl bg-white p-3"><span>ثبت امتیاز IMDb از TMDB</span><input v-model="importer.fetch_imdb_ratings" type="checkbox" class="size-4 accent-[var(--admin-primary)]" ></label>
            <p class="rounded-xl border border-teal-200 bg-teal-50 p-3 font-normal leading-6 text-teal-900">امتیاز نمایشی از میانگین رأی TMDB گرفته می‌شود. اگر عنوان یا خلاصه فارسی در TMDB نباشد، ایمپورتر آن را فارسی می‌کند.</p>
            <label class="flex cursor-pointer items-center justify-between gap-3 rounded-xl bg-white p-3"><span>افزودن ترندها به اسلایدر</span><input v-model="importer.feature_trending" type="checkbox" class="size-4 accent-[var(--admin-primary)]" ></label>
            <label class="flex cursor-pointer items-center justify-between gap-3 rounded-xl bg-white p-3"><span>انتشار خودکار متادیتای کامل</span><input v-model="importer.auto_publish" type="checkbox" class="size-4 accent-[var(--admin-primary)]" ></label>
          </div>
        </section>
      </div>

      <section class="mt-5 rounded-2xl border border-[var(--admin-border)] p-4">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-end">
          <label class="flex min-h-11 flex-1 cursor-pointer items-center justify-between gap-3 rounded-xl bg-[var(--admin-surface-muted)] px-4 text-sm font-black"><span>اجرای خودکار زمان‌بندی‌شده</span><input v-model="importer.automation_enabled" type="checkbox" class="size-4 accent-[var(--admin-primary)]" ></label>
          <AdminField class="w-full sm:w-52" label="نوع اجرای خودکار"><select v-model="importer.automation_mode" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 text-sm"><option value="daily">جدیدهای روز</option><option value="trending">ترندها</option></select></AdminField>
          <AdminField class="w-full sm:w-52" label="فاصله اجرا (ساعت)"><input v-model.number="importer.automation_interval_hours" type="number" min="1" max="168" class="admin-focus h-11 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 font-latin text-sm" ></AdminField>
        </div>
      </section>
    </AdminCard>

    <AdminCard class="mt-6 overflow-hidden">
      <div class="border-b border-[var(--admin-border)] px-5 py-4"><h2 class="font-black">اجراهای اخیر</h2></div>
      <div v-if="!runs.length && !loading" class="p-8 text-center text-sm text-[var(--admin-muted)]">هنوز اجرایی ثبت نشده است.</div>
      <div v-else class="responsive-table"><table class="w-full min-w-[760px] text-right text-xs"><thead class="bg-[var(--admin-surface-muted)] text-[var(--admin-muted)]"><tr><th class="px-5 py-3">اجرا</th><th class="px-4 py-3">نوع</th><th class="px-4 py-3">وضعیت</th><th class="px-4 py-3">پیشرفت</th><th class="px-4 py-3">ساخته / به‌روز</th><th class="px-5 py-3">زمان</th></tr></thead><tbody class="divide-y divide-[var(--admin-border)]"><tr v-for="run in runs" :key="run.id"><td class="px-5 py-4 font-bold">#{{ run.id.toLocaleString('fa-IR') }}</td><td class="px-4 py-4">{{ modeLabels[run.mode] }}</td><td class="px-4 py-4"><AdminBadge :tone="run.status">{{ statusLabels[run.status] }}</AdminBadge></td><td class="px-4 py-4 font-latin">{{ formatNumber(run.processed_count) }} / {{ formatNumber(run.total_count) }}</td><td class="px-4 py-4"><span class="text-emerald-700">{{ formatNumber(run.created_count) }}</span> / <span class="text-teal-800">{{ formatNumber(run.updated_count) }}</span></td><td class="px-5 py-4 text-[var(--admin-muted)]">{{ new Date(run.started_at).toLocaleString('fa-IR') }}</td></tr></tbody></table></div>
    </AdminCard>
  </div>
</template>

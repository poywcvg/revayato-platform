<script setup lang="ts">
import AlertTriangle from '~icons/lucide/triangle-alert'
import Check from '~icons/lucide/check'
import Download from '~icons/lucide/download'
import HardDrive from '~icons/lucide/hard-drive'
import Refresh from '~icons/lucide/rotate-cw'
import Search from '~icons/lucide/search'
import ShieldAlert from '~icons/lucide/shield-alert'
import Square from '~icons/lucide/square'
import type {
  AppErrorDetails,
  ProviderImportItem,
  ProviderImportJob,
  ProviderImportLog,
  ProviderSource,
  ProviderValidateResult,
} from '~/types'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'ورود از ارائه‌دهنده', robots: 'noindex, nofollow' })

const api = useProviderImport()
const notifications = useNotifications()

const sources = ref<ProviderSource[]>([])
const jobs = ref<ProviderImportJob[]>([])
const items = ref<ProviderImportItem[]>([])
const logs = ref<ProviderImportLog[]>([])
const validateResult = ref<ProviderValidateResult | null>(null)
const loading = ref(true)
const actionLoading = ref(false)
const error = ref<AppErrorDetails | null>(null)

const contentType = ref<'movies' | 'series' | 'both'>('movies')
const limit = ref(100)
const dryRun = ref(true)
const overwrite = ref(false)
const qualityPreference = ref('1080p,720p')

const jobsPolling = usePolling(() => void loadJobs(true), { intervalMs: 2500, immediate: false })

const avasarami = computed(() => sources.value.find(s => s.slug === 'avasarami') || null)
const activeJob = computed(() => jobs.value.find(job => job.is_active) || null)
const focusJob = computed(() => activeJob.value || jobs.value[0] || null)
const captchaWarning = computed(() => Boolean(
  validateResult.value?.requires_interactive_verification
  || avasarami.value?.credential_status === 'needs_interactive',
))

const statusLabels: Record<string, string> = {
  queued: 'در صف',
  validating: 'اعتبارسنجی',
  searching: 'جستجو',
  awaiting_review: 'منتظر تأیید',
  running: 'در حال اجرا',
  transferring: 'انتقال',
  cancel_requested: 'درخواست لغو',
  completed: 'کامل‌شده',
  partially_completed: 'ناقص کامل',
  blocked: 'مسدود',
  failed: 'ناموفق',
  cancelled: 'لغوشده',
}

function qualityList() {
  return qualityPreference.value
    .split(',')
    .map(part => part.trim())
    .filter(Boolean)
}

function secretLabel(configured: boolean) {
  return configured ? 'تنظیم شده' : 'تنظیم نشده'
}

async function loadSources(silent = false) {
  if (!silent) loading.value = true
  try {
    const response = await api.listSources()
    sources.value = response.results
    error.value = null
  } catch (cause) {
    if (!silent) error.value = getAppError(cause, 'فهرست ارائه‌دهنده دریافت نشد.')
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadJobs(silent = false) {
  try {
    const response = await api.listJobs()
    jobs.value = response.results
    const focus = activeJob.value || jobs.value[0]
    if (focus) {
      const [itemRes, logRes] = await Promise.all([
        api.jobItems(focus.id),
        api.jobLogs(focus.id),
      ])
      items.value = itemRes.results
      logs.value = logRes.results
    }
  } catch (cause) {
    if (!silent) error.value = getAppError(cause, 'وضعیت job دریافت نشد.')
  }
}

async function validateConnection() {
  if (!avasarami.value) return
  actionLoading.value = true
  try {
    validateResult.value = await api.validateSource(avasarami.value.id)
    await loadSources(true)
    if (validateResult.value.ok) {
      notifications.success('اتصال معتبر است', validateResult.value.message)
    } else if (validateResult.value.requires_interactive_verification) {
      notifications.error('نیاز به تأیید تعاملی', 'اعتبارسنجی نیاز به تأیید دستی دارد.', {
        reason: validateResult.value.message,
        inbox: true,
      })
    } else {
      notifications.error('اعتبارسنجی ناموفق', 'منبع تأیید نشد.', {
        reason: validateResult.value.message,
        inbox: true,
      })
    }
  } catch (cause) {
    const details = notifications.notifyError(cause, 'اعتبارسنجی انجام نشد.')
    validateResult.value = {
      ok: false,
      message: details.message,
      requires_interactive_verification: /captcha|interactive/i.test(details.message),
    }
  } finally {
    actionLoading.value = false
  }
}

async function approveCandidate(candidateId: number) {
  if (!focusJob.value) return
  actionLoading.value = true
  try {
    await api.approveMatch(focusJob.value.id, candidateId)
    notifications.success('تأیید شد', 'کاندید علامت‌گذاری شد.')
    await loadJobs(true)
  } catch (cause) {
    notifications.notifyError(cause, 'تأیید انجام نشد')
  } finally {
    actionLoading.value = false
  }
}

async function runDiscover() {
  if (!avasarami.value) return
  actionLoading.value = true
  try {
    const job = await api.discover(avasarami.value.id, {
      content_type: contentType.value,
      limit: limit.value,
      dry_run: true,
    })
    jobs.value = [job, ...jobs.value.filter(item => item.id !== job.id)]
    notifications.success('کشف آغاز شد', 'فهرست مجاز ارائه‌دهنده در حال دریافت است.')
    await loadJobs(true)
  } catch (cause) {
    notifications.notifyError(cause, 'کشف شروع نشد')
  } finally {
    actionLoading.value = false
  }
}

async function runImport() {
  if (!avasarami.value) return
  actionLoading.value = true
  try {
    const job = await api.startImport(avasarami.value.id, {
      content_type: contentType.value,
      limit: limit.value,
      dry_run: dryRun.value,
      overwrite: overwrite.value,
      quality_preference: qualityList(),
    })
    jobs.value = [job, ...jobs.value.filter(item => item.id !== job.id)]
    notifications.success(
      dryRun.value ? 'شبیه‌سازی آغاز شد' : 'ورود فایل آغاز شد',
      'job در صف Celery قرار گرفت.',
    )
    await loadJobs(true)
  } catch (cause) {
    notifications.notifyError(cause, 'ورود شروع نشد')
  } finally {
    actionLoading.value = false
  }
}

async function cancelActiveJob() {
  if (!activeJob.value) return
  actionLoading.value = true
  try {
    const job = await api.cancelJob(activeJob.value.id)
    jobs.value = jobs.value.map(item => item.id === job.id ? job : item)
    notifications.success('درخواست لغو ثبت شد', 'پس از آیتم فعلی متوقف می‌شود.')
  } catch (cause) {
    notifications.notifyError(cause, 'لغو انجام نشد')
  } finally {
    actionLoading.value = false
  }
}

await Promise.all([loadSources(), loadJobs()])
onMounted(() => { jobsPolling.start() })
</script>

<template>
  <div class="px-4 py-6 sm:px-6 lg:px-8 lg:py-9">
    <header class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div class="min-w-0">
        <div class="mb-2 flex flex-wrap items-center gap-2 text-xs font-bold text-[var(--admin-muted)]">
          <span>استودیو روایتو</span><span>/</span><span class="text-[var(--admin-primary)]">ارائه‌دهنده مجاز</span>
        </div>
        <h1 class="text-2xl font-black tracking-tight sm:text-3xl">ورود از ارائه‌دهنده مجاز</h1>
        <p class="mt-2 max-w-3xl text-sm leading-7 text-[var(--admin-muted)]">
          Avasarami — فقط دسترسی مجاز. CAPTCHA/Cloudflare دور زده نمی‌شود.
          کانال تلگرام دنیای سریال برای کشف و اضافه کردن فیلم/سریال با لینک دانلود عمومی.
          برای لینک‌های Film2Media (myf2m) از بخش رسانه در صفحه ویرایش فیلم یا سریال استفاده کنید.
        </p>
      </div>
      <AdminButton class="w-full shrink-0 sm:w-auto" variant="secondary" :disabled="loading" @click="loadSources()">
        <template #icon><Refresh class="size-4" :class="loading && 'animate-spin'" /></template>
        تازه‌سازی
      </AdminButton>
    </header>

    <p v-if="error" class="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      {{ error.message }}
    </p>

    <section v-if="avasarami" class="mt-6 rounded-2xl border border-[var(--admin-border)] bg-white p-5 shadow-sm">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="text-lg font-black">{{ avasarami.name }}</h2>
          <p class="mt-1 text-xs font-bold text-[var(--admin-muted)]">{{ avasarami.slug }} · {{ avasarami.auth_type || 'none' }}</p>
        </div>
        <AdminButton :disabled="actionLoading" @click="validateConnection">
          <template #icon><Check class="size-4" /></template>
          اعتبارسنجی اتصال
        </AdminButton>
      </div>

      <dl class="mt-5 grid gap-3 text-sm sm:grid-cols-2">
        <div><dt class="text-[var(--admin-muted)]">Base URL</dt><dd class="font-bold break-all">{{ avasarami.base_url }}</dd></div>
        <div><dt class="text-[var(--admin-muted)]">Login URL</dt><dd class="font-bold break-all">{{ avasarami.login_url }}</dd></div>
        <div><dt class="text-[var(--admin-muted)]">Movies URL</dt><dd class="font-bold break-all">{{ avasarami.movies_url }}</dd></div>
        <div><dt class="text-[var(--admin-muted)]">Series URL</dt><dd class="font-bold break-all">{{ avasarami.series_url }}</dd></div>
      </dl>

      <div class="mt-5 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-xl border border-[var(--admin-border)] px-3 py-2">
          API token: <strong>{{ secretLabel(avasarami.secrets.api_token_configured) }}</strong>
        </div>
        <div class="rounded-xl border border-[var(--admin-border)] px-3 py-2">
          Cookie/session: <strong>{{ secretLabel(avasarami.secrets.cookie_configured) }}</strong>
        </div>
        <div class="rounded-xl border border-[var(--admin-border)] px-3 py-2">
          Username: <strong>{{ secretLabel(avasarami.secrets.username_configured) }}</strong>
        </div>
        <div class="rounded-xl border border-[var(--admin-border)] px-3 py-2">
          Password: <strong>{{ secretLabel(avasarami.secrets.password_configured) }}</strong>
        </div>
      </div>

      <div
        v-if="captchaWarning"
        class="mt-5 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
      >
        <ShieldAlert class="mt-0.5 size-5 shrink-0" />
        <p>
          Avasarami login requires CAPTCHA. Please configure official API token, authorized cookie/session, or provider feed.
        </p>
      </div>

      <p v-if="validateResult" class="mt-4 text-sm" :class="validateResult.ok ? 'text-emerald-700' : 'text-amber-800'">
        {{ validateResult.message }}
      </p>
    </section>

    <section class="mt-6 rounded-2xl border border-[var(--admin-border)] bg-white p-5 shadow-sm">
      <h2 class="text-lg font-black">کشف و ورود</h2>
      <div class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label class="text-sm">
          <span class="mb-1 block text-[var(--admin-muted)]">نوع محتوا</span>
          <select v-model="contentType" class="admin-input w-full">
            <option value="movies">فیلم</option>
            <option value="series">سریال</option>
            <option value="both">هر دو</option>
          </select>
        </label>
        <label class="text-sm">
          <span class="mb-1 block text-[var(--admin-muted)]">محدودیت</span>
          <input v-model.number="limit" class="admin-input w-full" type="number" min="1" max="500">
        </label>
        <label class="text-sm">
          <span class="mb-1 block text-[var(--admin-muted)]">ترجیح کیفیت</span>
          <input v-model="qualityPreference" class="admin-input w-full" type="text" placeholder="1080p,720p">
        </label>
        <div class="flex flex-col justify-end gap-2 text-sm">
          <label class="flex min-h-11 items-center gap-2"><input v-model="dryRun" type="checkbox"> Dry-run</label>
          <label class="flex min-h-11 items-center gap-2"><input v-model="overwrite" type="checkbox"> Overwrite آرشیو</label>
        </div>
      </div>
      <div class="mt-5 flex flex-wrap gap-3">
        <AdminButton :disabled="actionLoading || !avasarami" @click="runDiscover">
          <template #icon><Search class="size-4" /></template>
          کشف
        </AdminButton>
        <AdminButton :disabled="actionLoading || !avasarami" variant="secondary" @click="runImport">
          <template #icon><Download class="size-4" /></template>
          ورود فایل‌های مفقود
        </AdminButton>
        <AdminButton :disabled="actionLoading || !activeJob" variant="danger" @click="cancelActiveJob">
          <template #icon><Square class="size-4" /></template>
          لغو job
        </AdminButton>
      </div>
    </section>

    <section v-if="focusJob" class="mt-6 rounded-2xl border border-[var(--admin-border)] bg-white p-5 shadow-sm">
      <template v-for="job in (focusJob ? [focusJob] : [])" :key="job.id">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-lg font-black">پیشرفت job</h2>
          <span class="text-xs font-bold text-[var(--admin-muted)]">
            {{ statusLabels[job.status] }}
          </span>
        </div>
        <div class="mt-4 grid gap-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
          <div><span class="text-[var(--admin-muted)]">کل</span><p class="font-black">{{ job.total_items }}</p></div>
          <div><span class="text-[var(--admin-muted)]">پردازش</span><p class="font-black">{{ job.processed_items }}</p></div>
          <div><span class="text-[var(--admin-muted)]">تطبیق</span><p class="font-black">{{ job.matched_items }}</p></div>
          <div><span class="text-[var(--admin-muted)]">ورود</span><p class="font-black">{{ job.imported_files }}</p></div>
          <div><span class="text-[var(--admin-muted)]">رد شده</span><p class="font-black">{{ job.skipped_items }}</p></div>
          <div><span class="text-[var(--admin-muted)]">خطا</span><p class="font-black">{{ job.failed_items }}</p></div>
        </div>
        <p v-if="job.current_item_label" class="mt-3 text-sm text-[var(--admin-muted)]">
          آیتم فعلی: {{ job.current_item_label }}
        </p>
        <p v-if="job.error_message" class="mt-3 flex gap-2 text-sm text-red-700">
          <AlertTriangle class="size-4 shrink-0" />
          {{ job.error_message }}
        </p>
      </template>
    </section>

    <section class="mt-6 overflow-hidden rounded-2xl border border-[var(--admin-border)] bg-white shadow-sm">
      <div class="border-b border-[var(--admin-border)] px-5 py-4">
        <h2 class="text-lg font-black">آیتم‌ها</h2>
      </div>
      <div class="responsive-table">
        <table class="min-w-[760px] text-sm">
          <thead class="bg-[var(--admin-bg)] text-[var(--admin-muted)]">
            <tr>
              <th class="px-4 py-3 text-right font-bold">عنوان</th>
              <th class="px-4 py-3 text-right font-bold">سال</th>
              <th class="px-4 py-3 text-right font-bold">امتیاز</th>
              <th class="px-4 py-3 text-right font-bold">وضعیت</th>
              <th class="px-4 py-3 text-right font-bold">پیام</th>
              <th class="px-4 py-3 text-right font-bold">عملیات</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.id" class="border-t border-[var(--admin-border)]">
              <td class="px-4 py-3 font-bold">{{ item.title || item.provider_item_id }}</td>
              <td class="px-4 py-3">{{ item.year || '—' }}</td>
              <td class="px-4 py-3" dir="ltr">{{ item.match_score != null ? item.match_score.toFixed(2) : '—' }}</td>
              <td class="px-4 py-3">{{ item.status }}</td>
              <td class="px-4 py-3 text-[var(--admin-muted)]">{{ item.status_message || '—' }}</td>
              <td class="px-4 py-3">
                <AdminButton
                  v-if="item.status !== 'approved' && item.status !== 'skipped' && focusJob"
                  size="sm"
                  variant="secondary"
                  :disabled="actionLoading"
                  @click="approveCandidate(item.id)"
                >
                  تأیید
                </AdminButton>
                <span v-else-if="item.status === 'approved'" class="text-xs font-bold text-emerald-700">تأیید شده</span>
                <span v-else class="text-[var(--admin-muted)]">—</span>
              </td>
            </tr>
            <tr v-if="!items.length">
              <td colspan="6" class="px-4 py-8 text-center text-[var(--admin-muted)]">آیتمی ثبت نشده است.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="mt-6 rounded-2xl border border-[var(--admin-border)] bg-white p-5 shadow-sm">
      <h2 class="mb-3 flex items-center gap-2 text-lg font-black">
        <HardDrive class="size-5" />
        لاگ‌های امن
      </h2>
      <ul class="space-y-2 text-sm">
        <li v-for="entry in logs" :key="entry.id" class="rounded-xl border border-[var(--admin-border)] px-3 py-2">
          <span class="font-bold uppercase text-[var(--admin-muted)]">{{ entry.level }}</span>
          — {{ entry.message }}
        </li>
        <li v-if="!logs.length" class="text-[var(--admin-muted)]">لاگی موجود نیست.</li>
      </ul>
    </section>
  </div>
</template>

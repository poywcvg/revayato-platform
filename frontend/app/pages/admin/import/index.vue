<script setup lang="ts">
/**
 * Staff import desk.
 *
 * Everything needed to put a title on the site lives here, in the order a
 * person actually thinks in: search for the title, look at it to be sure it
 * is the right one, bring in the metadata, then send the crawlers after the
 * playable links. Each step reports what it did, because every one of them
 * can partly succeed — a title can import cleanly and still have no source,
 * and that is worth seeing.
 *
 * Two more tabs sit next to the search desk and share its job feed:
 * «ایمپورترها» manages the provider connectors themselves (validate the
 * connection, run a discover/import across the provider), and «اجرای گروهی»
 * runs the bulk jobs (catalog year import, TMDB sync runs) plus the importer
 * settings. The per-title editors (`/admin/movies/[id]`, `/admin/series/[id]`)
 * stay where they were — this page gets titles *in*, those pages keep them
 * correct.
 */
import type {
  CatalogImporterSettings,
  CatalogSyncMode,
  CatalogSyncRun,
  ProviderImportJob,
  ProviderJobStatus,
  ProviderSource,
  ProviderValidateResult,
  TmdbPreview,
  TmdbSearchResponse,
  TmdbSearchRow,
} from '~/types/admin'
import DownloadCloud from '~icons/lucide/download-cloud'
import Search from '~icons/lucide/search'
import Film from '~icons/lucide/film'
import Tv from '~icons/lucide/tv'
import Star from '~icons/lucide/star'
import Radar from '~icons/lucide/radar'
import Check from '~icons/lucide/check'
import X from '~icons/lucide/x'
import Loader from '~icons/lucide/loader-circle'
import ExternalLink from '~icons/lucide/external-link'
import Pencil from '~icons/lucide/pencil'
import Server from '~icons/lucide/server'
import Layers from '~icons/lucide/layers'
import Play from '~icons/lucide/play'
import Square from '~icons/lucide/square'
import Settings from '~icons/lucide/settings'
import Plus from '~icons/lucide/plus'
import RefreshCw from '~icons/lucide/refresh-cw'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'ورود محتوا — روایتو' })

const { api } = useApi()
const notify = useNotifications()

const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

/* --- tabs ------------------------------------------------------------------ */

type DeskTab = 'search' | 'sources' | 'bulk'
const tab = ref<DeskTab>('search')
const TABS: { value: DeskTab, label: string }[] = [
  { value: 'search', label: 'جستجو و ورود' },
  { value: 'sources', label: 'ایمپورترها' },
  { value: 'bulk', label: 'اجرای گروهی' },
]

/* --- search --------------------------------------------------------------- */

type Kind = 'all' | 'movie' | 'series'
const KINDS: { value: Kind, label: string }[] = [
  { value: 'all', label: 'همه' },
  { value: 'movie', label: 'فیلم' },
  { value: 'series', label: 'سریال' },
]

const query = ref('')
const kind = ref<Kind>('all')
const searching = ref(false)
const searchError = ref('')
const results = ref<TmdbSearchRow[]>([])
const searched = ref(false)

async function runSearch() {
  const q = query.value.trim()
  if (!q) return
  searching.value = true
  searchError.value = ''
  try {
    const response = await api<TmdbSearchResponse>('/admin/tmdb/search/', {
      query: { query: q, kind: kind.value },
    })
    results.value = response?.results ?? []
    searched.value = true
  }
  catch {
    searchError.value = 'جستجو در TMDB ناموفق بود. اتصال یا کلید API را بررسی کنید.'
    results.value = []
  }
  finally {
    searching.value = false
  }
}

// Re-run on a kind switch, but only once a search has actually happened —
// flipping the filter before typing anything should not fire a request.
watch(kind, () => { if (searched.value && query.value.trim()) runSearch() })

const yearOf = (row: { release_date?: string }) => (row.release_date || '').slice(0, 4)

/* --- preview + import ----------------------------------------------------- */

const selected = ref<TmdbSearchRow | null>(null)
const preview = ref<TmdbPreview | null>(null)
const previewing = ref(false)
const importing = ref(false)
/** Publish on import. Off by default: a title with no verified source should
 *  not go live, and sources are only fetched in the next step. */
const publishNow = ref(false)
/** Overwrite fields a person edited by hand. Off by default for that reason. */
const overwriteManual = ref(false)
/** The catalog row that exists for the selected title, after import or before. */
const localItem = ref<{ id: number, slug: string, title: string } | null>(null)

async function openPreview(row: TmdbSearchRow) {
  selected.value = row
  preview.value = null
  localItem.value = row.local_item ?? null
  previewing.value = true
  const path = row.kind === 'series'
    ? `/admin/tmdb/series/${row.tmdb_id}/preview/`
    : `/admin/tmdb/movie/${row.tmdb_id}/preview/`
  try {
    const data = await api<TmdbPreview>(path)
    preview.value = data
    localItem.value = data?.local_item ?? data?.local_movie ?? localItem.value
  }
  catch {
    notify.error('خطا', 'دریافت جزئیات از TMDB ناموفق بود')
    selected.value = null
  }
  finally {
    previewing.value = false
  }
}

function closePreview() {
  selected.value = null
  preview.value = null
}

async function runImport() {
  const row = selected.value
  if (!row) return
  importing.value = true
  const path = row.kind === 'series'
    ? `/admin/tmdb/series/${row.tmdb_id}/import/`
    : `/admin/tmdb/movie/${row.tmdb_id}/import/`
  try {
    const response = await api<{ movie?: Record<string, unknown>, series?: Record<string, unknown>, item?: Record<string, unknown> }>(path, {
      method: 'POST',
      body: { publish: publishNow.value, overwrite_manual: overwriteManual.value },
    })
    const created = (response?.movie || response?.series || response?.item || {}) as {
      id?: number, slug?: string, title?: string
    }
    if (created?.id) {
      localItem.value = { id: created.id, slug: created.slug || '', title: created.title || row.title }
    }
    notify.success('وارد شد', `«${row.title}» به کتابخانه افزوده شد`)
    // Reflect it in the result list without a second round trip.
    const hit = results.value.find(r => r.tmdb_id === row.tmdb_id && r.kind === row.kind)
    if (hit) {
      hit.already_imported = true
      hit.local_item = localItem.value
    }
  }
  catch (error) {
    const detail = (error as { data?: { detail?: string } })?.data?.detail
    notify.error('ورود ناموفق بود', detail || 'TMDB یا پایگاه داده پاسخ نداد')
  }
  finally {
    importing.value = false
  }
}

/* --- sending the crawlers after the playable links ------------------------ */

const discovering = ref(false)

/**
 * Queue a provider crawl for the imported title.
 *
 * This is the half that decides whether anyone can actually watch it. The
 * metadata import above only creates the catalog row; the file lives on a
 * provider and has to be found, and the links it yields go through the same
 * verification gate as every automated import — so a title only becomes
 * playable here if its sources really work.
 */
async function discoverSources() {
  const row = selected.value
  const local = localItem.value
  if (!row || !local?.id) return
  discovering.value = true
  const path = row.kind === 'series'
    ? `/admin/catalog/series/${local.id}/provider-discover/`
    : `/admin/catalog/movies/${local.id}/provider-discover/`
  try {
    const job = await api<ProviderImportJob>(path, {
      method: 'POST',
      body: { force: true, mode: 'discover_only' },
    })
    notify.success('خزنده اجرا شد', 'جستجوی لینک‌های پخش آغاز شد؛ نتیجه در فهرست پایین دیده می‌شود.')
    if (job?.id) jobs.value = [job, ...jobs.value.filter(j => j.id !== job.id)].slice(0, 20)
    startJobPolling()
  }
  catch (error) {
    const detail = (error as { data?: { detail?: string } })?.data?.detail
    notify.error('اجرای خزنده ناموفق بود', detail || 'صف پردازش در دسترس نیست')
  }
  finally {
    discovering.value = false
  }
}

/* --- job feed ------------------------------------------------------------- */

const jobs = ref<ProviderImportJob[]>([])
const jobsError = ref(false)
const cancellingJob = ref('')
let jobTimer: ReturnType<typeof setInterval> | undefined

// The job vocabulary lives in `useAdminOps` so this console and the operations
// page never disagree about what a status is called.
const JOB_TONE = JOB_STATUS_TONE
const JOB_LABEL = JOB_STATUS_LABEL

const LIVE_JOB_STATUSES: ProviderJobStatus[] = [
  'queued', 'validating', 'searching', 'awaiting_review', 'running', 'transferring', 'cancel_requested',
]

const hasLiveJob = computed(() =>
  jobs.value.some(job => LIVE_JOB_STATUSES.includes(job.status)),
)

function jobTarget(job: ProviderImportJob): string {
  if (job.target_movie) return `فیلم #${job.target_movie}`
  if (job.target_series) return `سریال #${job.target_series}`
  if (job.object_id) return `#${job.object_id}`
  const type = job.content_type === 'series' || job.content_type === 'serie' ? 'سریال' : job.content_type === 'both' ? 'فیلم و سریال' : 'فیلم'
  return type
}

function jobImported(job: ProviderImportJob): number {
  return Number(job.imported_files ?? job.imported_items ?? 0)
}

async function loadJobs() {
  try {
    const response = await api<{ results?: ProviderImportJob[] } | ProviderImportJob[]>(
      '/admin/provider-import/jobs/', { query: { limit: 20 } },
    )
    jobs.value = Array.isArray(response) ? response : (response?.results ?? [])
    jobsError.value = false
  }
  catch { jobsError.value = true }
}

/** Poll only while something is actually running, and stop when it settles. */
function startJobPolling() {
  if (jobTimer) return
  jobTimer = setInterval(async () => {
    await loadJobs()
    if (!hasLiveJob.value) {
      clearInterval(jobTimer)
      jobTimer = undefined
    }
  }, 4000)
}

async function cancelJob(job: ProviderImportJob) {
  if (!LIVE_JOB_STATUSES.includes(job.status)) return
  if (!window.confirm('این اجرا لغو شود؟')) return
  cancellingJob.value = job.id
  try {
    const updated = await api<ProviderImportJob>(`/admin/provider-import/jobs/${job.id}/cancel/`, { method: 'POST' })
    jobs.value = jobs.value.map(j => j.id === job.id ? updated : j)
    notify.success('لغو شد', 'اجرا متوقف شد')
  }
  catch {
    notify.error('خطا', 'لغو اجرا ناموفق بود')
  }
  finally {
    cancellingJob.value = ''
  }
}

onMounted(async () => {
  await loadJobs()
  if (hasLiveJob.value) startJobPolling()
})
onBeforeUnmount(() => { if (jobTimer) clearInterval(jobTimer) })

const editLinkFor = (row: TmdbSearchRow | null, local: { id: number } | null) =>
  (!row || !local) ? '' : (row.kind === 'series' ? `/admin/series/${local.id}` : `/admin/movies/${local.id}`)

/* --- sources (ایمپورترها) -------------------------------------------------- */

const sources = ref<ProviderSource[]>([])
const sourcesPending = ref(false)
const sourcesError = ref(false)
const sourcesLoaded = ref(false)
const validatingSource = ref(0)
const runningSource = ref(0)
const activeSourceId = ref<number | null>(null)
const showSourceCreate = ref(false)

const SOURCE_RUN_CONTENT_TYPES = [
  { value: 'movies', label: 'فیلم' },
  { value: 'series', label: 'سریال' },
  { value: 'both', label: 'هر دو' },
]
const sourceRun = ref({
  content_type: 'movies',
  limit: 100,
  dry_run: false,
  overwrite: false,
  quality_preference: '1080p,720p',
})
const sourceCreate = ref({
  name: '',
  base_url: '',
  provider_type: 'custom',
  auth_type: 'none',
  is_active: true,
})
const PROVIDER_TYPES = [
  { value: 'api', label: 'API' },
  { value: 'feed', label: 'فید' },
  { value: 'cookie_session', label: 'نشست کوکی' },
  { value: 'session_login', label: 'ورود نشستی' },
  { value: 'static_links', label: 'لینک ثابت' },
  { value: 'custom', label: 'سفارشی' },
]
const AUTH_TYPES = [
  { value: 'none', label: 'بدون احراز' },
  { value: 'api_key', label: 'کلید API' },
  { value: 'bearer_token', label: 'توکن Bearer' },
  { value: 'username_password', label: 'نام کاربری/گذرواژه' },
  { value: 'cookie_session', label: 'نشست کوکی' },
  { value: 'feed', label: 'فید' },
]


async function loadSources() {
  sourcesPending.value = true
  sourcesError.value = false
  try {
    const response = await api<{ results?: ProviderSource[] } | ProviderSource[]>('/admin/provider-sources/')
    sources.value = Array.isArray(response) ? response : (response?.results ?? [])
    sourcesLoaded.value = true
    if (activeSourceId.value == null && sources.value.length) {
      activeSourceId.value = sources.value[0]?.id ?? null
    }
  }
  catch { sourcesError.value = true }
  finally { sourcesPending.value = false }
}

watch(tab, (value) => {
  if (value === 'sources' && !sourcesLoaded.value) void loadSources()
  if (value === 'bulk' && !bulkLoaded.value) void loadBulk()
})

async function validateSource(source: ProviderSource) {
  validatingSource.value = source.id
  try {
    const result = await api<ProviderValidateResult>(`/admin/provider-sources/${source.id}/validate/`, { method: 'POST' })
    if (result?.ok) notify.success('اتصال معتبر است', result.message || 'ارائه‌دهنده پاسخ داد')
    else notify.error('اعتبارسنجی ناموفق بود', result?.message || 'اتصال برقرار نشد')
    await loadSources()
  }
  catch (error) {
    const data = (error as { data?: { message?: string } })?.data
    notify.error('اعتبارسنجی ناموفق بود', data?.message || 'اتصال برقرار نشد')
  }
  finally { validatingSource.value = 0 }
}

async function toggleSourceActive(source: ProviderSource) {
  try {
    const updated = await api<ProviderSource>(`/admin/provider-sources/${source.id}/`, {
      method: 'PATCH', body: { is_active: !source.is_active },
    })
    sources.value = sources.value.map(s => s.id === source.id ? updated : s)
    notify.success('انجام شد', updated.is_active ? 'ایمپورتر فعال شد' : 'ایمپورتر غیرفعال شد')
  }
  catch { notify.error('خطا', 'تغییر وضعیت ناموفق بود') }
}

async function runSourceJob(source: ProviderSource, runMode: 'discover_only' | 'import_missing_files') {
  runningSource.value = source.id
  try {
    const qualities = String(sourceRun.value.quality_preference || '').split(',').map(s => s.trim()).filter(Boolean)
    const job = await api<ProviderImportJob>(
      runMode === 'discover_only'
        ? `/admin/provider-sources/${source.id}/discover/`
        : `/admin/provider-sources/${source.id}/import/`,
      {
        method: 'POST',
        body: {
          content_type: sourceRun.value.content_type,
          mode: runMode,
          limit: Number(sourceRun.value.limit) || 100,
          dry_run: sourceRun.value.dry_run,
          overwrite: sourceRun.value.overwrite,
          quality_preference: qualities,
        },
      },
    )
    notify.success('در صف قرار گرفت', runMode === 'discover_only' ? 'کشف ارائه‌دهنده آغاز شد' : 'ورود از ارائه‌دهنده آغاز شد')
    if (job?.id) jobs.value = [job, ...jobs.value.filter(j => j.id !== job.id)].slice(0, 20)
    startJobPolling()
  }
  catch (error) {
    const detail = (error as { data?: { detail?: string } })?.data?.detail
    notify.error('اجرا ناموفق بود', detail || 'صف پردازش در دسترس نیست')
  }
  finally { runningSource.value = 0 }
}

async function createSource() {
  const name = sourceCreate.value.name.trim()
  if (!name) {
    notify.error('خطا', 'نام ایمپورتر لازم است')
    return
  }
  try {
    const created = await api<ProviderSource>('/admin/provider-sources/', {
      method: 'POST',
      body: {
        name,
        base_url: sourceCreate.value.base_url.trim(),
        provider_type: sourceCreate.value.provider_type,
        auth_type: sourceCreate.value.auth_type,
        is_active: sourceCreate.value.is_active,
      },
    })
    sources.value = [...sources.value, created].sort((a, b) => a.name.localeCompare(b.name, 'fa'))
    activeSourceId.value = created.id
    showSourceCreate.value = false
    sourceCreate.value = { name: '', base_url: '', provider_type: 'custom', auth_type: 'none', is_active: true }
    notify.success('ساخته شد', 'ایمپورتر جدید افزوده شد')
  }
  catch (error) {
    const detail = (error as { data?: { detail?: string } })?.data?.detail
    notify.error('ساخت ناموفق بود', detail || 'اعتبارسنجی ناموفق بود')
  }
}

/* --- bulk (اجرای گروهی) ----------------------------------------------------- */

const bulkLoaded = ref(false)
const yearForm = ref({
  content_type: 'both',
  providers: ['dornatv', 'myf2m'] as string[],
  year_start: '',
  year_end: '',
  discover: true,
  enrich: true,
  softsub: true,
  dornatv_rounds: 8,
  movies_per_round: 40,
  series_per_round: 20,
  myf2m_rounds: 6,
  myf2m_movies_per_round: 25,
  myf2m_series_per_round: 12,
  myf2m_pages_per_round: 12,
  enrich_limit: 0,
  delay: 0.35,
})
const startingYearImport = ref(false)

const syncRuns = ref<CatalogSyncRun[]>([])
const syncRunsError = ref(false)
const syncStarting = ref(false)
const syncCancelling = ref(0)
const syncForm = ref({
  mode: 'daily' as CatalogSyncMode,
  lookback_days: 3,
  lookahead_days: 30,
  max_pages: 10,
  window: 'week',
  confirm_full: false,
})
const SYNC_MODES: { value: CatalogSyncMode, label: string }[] = [
  { value: 'daily', label: 'روزانه' },
  { value: 'trending', label: 'ترندها' },
  { value: 'incremental', label: 'افزایشی' },
  { value: 'full', label: 'کامل' },
]
const SYNC_STATUS_LABEL = SYNC_RUN_LABEL
const SYNC_STATUS_TONE = SYNC_RUN_TONE

const importerSettings = ref<CatalogImporterSettings | null>(null)
const settingsSaving = ref(false)

async function loadBulk() {
  bulkLoaded.value = true
  await Promise.all([loadSyncRuns(), loadImporterSettings()])
}

async function loadSyncRuns() {
  try {
    const response = await api<{ results?: CatalogSyncRun[] }>('/admin/catalog-sync/runs/', { query: { limit: 10 } })
    syncRuns.value = response?.results ?? []
    syncRunsError.value = false
  }
  catch { syncRunsError.value = true }
}

async function loadImporterSettings() {
  try {
    importerSettings.value = await api<CatalogImporterSettings>('/admin/catalog-sync/settings/')
  }
  catch { importerSettings.value = null }
}

async function startYearImport() {
  startingYearImport.value = true
  try {
    const yearStart = yearForm.value.year_start ? Number(yearForm.value.year_start) : null
    const yearEnd = yearForm.value.year_end ? Number(yearForm.value.year_end) : null
    const job = await api<ProviderImportJob>('/admin/provider-import/catalog-year/start/', {
      method: 'POST',
      body: {
        content_type: yearForm.value.content_type,
        providers: yearForm.value.providers,
        year_start: yearStart,
        year_end: yearEnd,
        discover: yearForm.value.discover,
        enrich: yearForm.value.enrich,
        softsub: yearForm.value.softsub,
        dornatv_rounds: Number(yearForm.value.dornatv_rounds) || 8,
        movies_per_round: Number(yearForm.value.movies_per_round) || 40,
        series_per_round: Number(yearForm.value.series_per_round) || 20,
        myf2m_rounds: Number(yearForm.value.myf2m_rounds) || 6,
        myf2m_movies_per_round: Number(yearForm.value.myf2m_movies_per_round) || 25,
        myf2m_series_per_round: Number(yearForm.value.myf2m_series_per_round) || 12,
        myf2m_pages_per_round: Number(yearForm.value.myf2m_pages_per_round) || 12,
        enrich_limit: Number(yearForm.value.enrich_limit) || 0,
        delay: Number(yearForm.value.delay) || 0.35,
      },
    })
    notify.success('در صف قرار گرفت', 'ایمپورت گروهی آغاز شد؛ پیشرفت در فهرست اجراها دیده می‌شود.')
    if (job?.id) jobs.value = [job as ProviderImportJob, ...jobs.value.filter(j => j.id !== job.id)].slice(0, 20)
    startJobPolling()
  }
  catch (error) {
    const detail = (error as { data?: { detail?: string } })?.data?.detail
    notify.error('اجرا ناموفق بود', detail || 'صف پردازش در دسترس نیست')
  }
  finally { startingYearImport.value = false }
}

async function startSyncRun() {
  syncStarting.value = true
  try {
    const body: Record<string, unknown> = { mode: syncForm.value.mode }
    if (syncForm.value.mode === 'full') body.confirm_full = syncForm.value.confirm_full
    if (syncForm.value.mode === 'daily' || syncForm.value.mode === 'incremental') {
      body.lookback_days = Number(syncForm.value.lookback_days) || 3
      body.lookahead_days = Number(syncForm.value.lookahead_days) || 0
      body.max_pages = Number(syncForm.value.max_pages) || 10
    }
    if (syncForm.value.mode === 'trending') {
      body.window = syncForm.value.window
      body.max_pages = Number(syncForm.value.max_pages) || 10
    }
    const run = await api<CatalogSyncRun>('/admin/catalog-sync/runs/', { method: 'POST', body })
    syncRuns.value = [run, ...syncRuns.value].slice(0, 10)
    notify.success('در صف قرار گرفت', 'هم‌گام‌سازی TMDB آغاز شد')
  }
  catch (error) {
    const detail = (error as { data?: { detail?: string } })?.data?.detail
    notify.error('اجرا ناموفق بود', detail || 'صف پردازش در دسترس نیست')
  }
  finally { syncStarting.value = false }
}

async function cancelSyncRun(run: CatalogSyncRun) {
  if (!run.can_cancel) return
  syncCancelling.value = run.id
  try {
    const updated = await api<CatalogSyncRun>(`/admin/catalog-sync/runs/${run.id}/cancel/`, { method: 'POST' })
    syncRuns.value = syncRuns.value.map(r => r.id === run.id ? updated : r)
    notify.success('لغو شد', 'اجرا متوقف شد')
  }
  catch { notify.error('خطا', 'لغو اجرا ناموفق بود') }
  finally { syncCancelling.value = 0 }
}

async function saveImporterSettings() {
  if (!importerSettings.value) return
  settingsSaving.value = true
  try {
    const s = importerSettings.value
    importerSettings.value = await api<CatalogImporterSettings>('/admin/catalog-sync/settings/', {
      method: 'PATCH',
      body: {
        language: s.language,
        fallback_language: s.fallback_language,
        region: s.region,
        daily_lookback_days: s.daily_lookback_days,
        daily_lookahead_days: s.daily_lookahead_days,
        daily_max_pages: s.daily_max_pages,
        trending_window: s.trending_window,
        trending_max_pages: s.trending_max_pages,
        import_people_images: s.import_people_images,
        cast_import_limit: s.cast_import_limit,
        fetch_imdb_ratings: s.fetch_imdb_ratings,
        feature_trending: s.feature_trending,
        auto_publish: s.auto_publish,
        automation_enabled: s.automation_enabled,
        automation_mode: s.automation_mode,
        automation_interval_hours: s.automation_interval_hours,
      },
    })
    notify.success('ذخیره شد', 'تنظیمات ایمپورتر به‌روزرسانی شد')
  }
  catch { notify.error('خطا', 'ذخیره تنظیمات ناموفق بود') }
  finally { settingsSaving.value = false }
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">ورود محتوا</h1>
      <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">
        جستجو در TMDB، افزودن به کتابخانه و اجرای خزنده برای یافتن لینک‌های پخش
      </p>
    </div>

    <!-- Tabs -->
    <div class="flex items-center gap-1 overflow-x-auto rounded-[var(--rv-radius-sm)] border border-[var(--rv-border)] bg-[var(--rv-surface)] p-1">
      <button
        v-for="option in TABS"
        :key="option.value"
        type="button"
        class="rv-focus flex-1 whitespace-nowrap rounded-[calc(var(--rv-radius-sm)-2px)] px-3 py-2 text-xs font-black transition"
        :style="tab === option.value
          ? { background: 'var(--rv-accent)', color: 'var(--rv-on-accent, #fff)' }
          : { color: 'var(--rv-muted)' }"
        @click="tab = option.value"
      >
        {{ option.label }}
      </button>
    </div>

    <template v-if="tab === 'search'">
      <!-- Search -->
      <RvPanel :icon="Search" title="جستجوی عنوان" subtitle="نام فیلم یا سریال را به انگلیسی یا فارسی بنویسید">
        <form class="flex flex-wrap items-center gap-3" @submit.prevent="runSearch">
          <div class="relative min-w-[220px] flex-1">
            <Search class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--rv-faint)]" />
            <input
              v-model="query"
              type="search"
              placeholder="مثلاً Dune یا تلماسه…"
              class="rv-input !pr-9"
              autofocus
            >
          </div>
          <div class="flex items-center gap-1 rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-3)] p-1">
            <button
              v-for="option in KINDS"
              :key="option.value"
              type="button"
              class="rv-focus rounded-[calc(var(--rv-radius-sm)-2px)] px-3 py-1.5 text-xs font-black transition"
              :style="kind === option.value
                ? { background: 'var(--rv-accent)', color: 'var(--rv-on-accent, #fff)' }
                : { color: 'var(--rv-muted)' }"
              @click="kind = option.value"
            >
              {{ option.label }}
            </button>
          </div>
          <button type="submit" class="rv-btn rv-btn--primary rv-focus" :disabled="searching || !query.trim()">
            <Loader v-if="searching" class="size-4 animate-spin" />
            <Search v-else class="size-4" />
            جستجو
          </button>
        </form>
      </RvPanel>

      <!-- Results -->
      <RvPanel v-if="searched || searching" :icon="DownloadCloud" title="نتایج">
        <template #actions>
          <span v-if="results.length" class="text-xs font-bold text-[var(--rv-muted)]">
            {{ fa(results.length) }} نتیجه
          </span>
        </template>

        <RvState v-if="searchError" kind="error" title="جستجو ناموفق بود" :message="searchError" @retry="runSearch()" />
        <div v-else-if="searching" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <div v-for="n in 6" :key="n" class="h-[104px] animate-pulse rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-3)]" />
        </div>
        <RvState
          v-else-if="!results.length"
          title="چیزی پیدا نشد"
          message="املای نام را بررسی کنید یا نام اصلی (انگلیسی) عنوان را امتحان کنید."
        />
        <div v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <button
            v-for="row in results"
            :key="`${row.kind}-${row.tmdb_id}`"
            type="button"
            class="rv-focus group flex gap-3 rounded-[var(--rv-radius-sm)] border border-[var(--rv-border)] bg-[var(--rv-surface-2)] p-2.5 text-right transition hover:border-[var(--rv-accent)]"
            @click="openPreview(row)"
          >
            <img
              v-if="row.poster_url"
              :src="row.poster_url"
              :alt="row.title"
              loading="lazy"
              class="size-[84px] shrink-0 rounded-[calc(var(--rv-radius-sm)-2px)] object-cover"
            >
            <span v-else class="grid size-[84px] shrink-0 place-items-center rounded-[calc(var(--rv-radius-sm)-2px)] bg-[var(--rv-surface-3)] text-[var(--rv-faint)]">
              <component :is="row.kind === 'series' ? Tv : Film" class="size-5" />
            </span>
            <span class="flex min-w-0 flex-1 flex-col gap-1.5">
              <span class="flex items-center gap-1.5">
                <component :is="row.kind === 'series' ? Tv : Film" class="size-3.5 shrink-0 text-[var(--rv-faint)]" />
                <span class="truncate text-sm font-black text-[var(--rv-text)]">{{ row.title }}</span>
              </span>
              <span class="flex flex-wrap items-center gap-1.5 text-xs font-bold text-[var(--rv-muted)]">
                <span v-if="yearOf(row)">{{ yearOf(row) }}</span>
                <span v-if="row.vote_average" class="inline-flex items-center gap-0.5">
                  <Star class="size-3" /> {{ row.vote_average?.toFixed(1) }}
                </span>
              </span>
              <span class="flex flex-wrap gap-1.5">
                <RvBadge v-if="row.already_imported" tone="success" dot>در کتابخانه</RvBadge>
                <RvBadge v-else tone="neutral">وارد نشده</RvBadge>
              </span>
            </span>
          </button>
        </div>
      </RvPanel>
    </template>

    <template v-else-if="tab === 'sources'">
      <!-- Provider sources -->
      <RvPanel :icon="Server" title="ایمپورترها" subtitle="اتصال ارائه‌دهنده‌ها و اجرای کشف/ورود روی هر کدام">
        <template #actions>
          <button type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs" :disabled="sourcesPending" @click="loadSources()">
            <RefreshCw class="size-3.5" :class="sourcesPending ? 'animate-spin' : ''" />
            تازه‌سازی
          </button>
          <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-8 !px-2.5 !text-xs" @click="showSourceCreate = !showSourceCreate">
            <Plus class="size-3.5" />
            ایمپورتر جدید
          </button>
        </template>

        <div v-if="showSourceCreate" class="mb-4 grid gap-3 rounded-[var(--rv-radius-sm)] border border-dashed border-[var(--rv-border)] p-3 sm:grid-cols-2">
          <label class="block">
            <span class="rv-label">نام</span>
            <input v-model="sourceCreate.name" type="text" class="rv-input mt-1.5" placeholder="مثلاً فیلم‌تومدیا">
          </label>
          <label class="block">
            <span class="rv-label">نشانی پایه</span>
            <input v-model="sourceCreate.base_url" type="url" dir="ltr" class="rv-input mt-1.5" placeholder="https://…">
          </label>
          <label class="block">
            <span class="rv-label">نوع</span>
            <select v-model="sourceCreate.provider_type" class="rv-input mt-1.5">
              <option v-for="o in PROVIDER_TYPES" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <label class="block">
            <span class="rv-label">احراز هویت</span>
            <select v-model="sourceCreate.auth_type" class="rv-input mt-1.5">
              <option v-for="o in AUTH_TYPES" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <div class="flex items-end justify-between gap-3 sm:col-span-2">
            <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
              <input v-model="sourceCreate.is_active" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              فعال
            </label>
            <button type="button" class="rv-btn rv-btn--primary rv-focus !min-h-9" @click="createSource">
              <Plus class="size-4" />
              ساخت ایمپورتر
            </button>
          </div>
        </div>

        <RvState v-if="sourcesError" kind="error" title="فهرست ایمپورترها خوانده نشد" @retry="loadSources()" />
        <div v-else-if="sourcesPending && !sources.length" class="space-y-2">
          <div v-for="n in 3" :key="n" class="h-16 animate-pulse rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-3)]" />
        </div>
        <RvState v-else-if="!sources.length" title="ایمپورتری ثبت نشده" />
        <ul v-else class="divide-y divide-[var(--rv-border)]">
          <li v-for="source in sources" :key="source.id" class="py-3 first:pt-0 last:pb-0">
            <div class="flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                class="rv-focus min-w-0 flex-1 text-right"
                @click="activeSourceId = activeSourceId === source.id ? null : source.id"
              >
                <span class="block truncate text-sm font-black text-[var(--rv-text)]">{{ source.name }}</span>
                <span class="mt-0.5 block truncate text-xs font-semibold text-[var(--rv-faint)]" dir="ltr">{{ source.base_url || source.slug }}</span>
              </button>
              <RvBadge :tone="source.is_active ? 'success' : 'neutral'" dot>
                {{ source.is_active ? 'فعال' : 'غیرفعال' }}
              </RvBadge>
              <RvBadge v-if="source.credential_status && source.credential_status !== 'unknown'" tone="info">
                {{ source.credential_status }}
              </RvBadge>
              <button
                type="button"
                class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
                :disabled="validatingSource === source.id"
                @click="validateSource(source)"
              >
                <Loader v-if="validatingSource === source.id" class="size-3.5 animate-spin" />
                بررسی اتصال
              </button>
              <button
                type="button"
                class="rv-btn rv-btn--subtle rv-focus !min-h-8 !px-2.5 !text-xs"
                @click="toggleSourceActive(source)"
              >
                {{ source.is_active ? 'غیرفعال' : 'فعال' }}
              </button>
            </div>
            <p v-if="source.last_validation_message" class="mt-1 truncate text-xs font-semibold text-[var(--rv-muted)]">
              {{ source.last_validation_message }}
            </p>

            <!-- Per-source run form -->
            <div v-if="activeSourceId === source.id" class="mt-3 grid gap-3 rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-2)] p-3 sm:grid-cols-2">
              <label class="block">
                <span class="rv-label">نوع محتوا</span>
                <select v-model="sourceRun.content_type" class="rv-input mt-1.5">
                  <option v-for="o in SOURCE_RUN_CONTENT_TYPES" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
              </label>
              <label class="block">
                <span class="rv-label">سقف آیتم</span>
                <input v-model.number="sourceRun.limit" type="number" min="1" max="500" dir="ltr" class="rv-input mt-1.5">
              </label>
              <label class="block sm:col-span-2">
                <span class="rv-label">ترجیح کیفیت (با ویرگول)</span>
                <input v-model="sourceRun.quality_preference" type="text" dir="ltr" class="rv-input mt-1.5" placeholder="1080p,720p">
              </label>
              <div class="flex flex-wrap gap-4 sm:col-span-2">
                <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
                  <input v-model="sourceRun.dry_run" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
                  خشک (بدون ذخیره)
                </label>
                <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
                  <input v-model="sourceRun.overwrite" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
                  بازنویسی
                </label>
              </div>
              <div class="flex flex-wrap gap-2 sm:col-span-2">
                <button
                  type="button"
                  class="rv-btn rv-btn--ghost rv-focus flex-1"
                  :disabled="runningSource === source.id"
                  @click="runSourceJob(source, 'discover_only')"
                >
                  <Loader v-if="runningSource === source.id" class="size-4 animate-spin" />
                  <Radar v-else class="size-4" />
                  کشف
                </button>
                <button
                  type="button"
                  class="rv-btn rv-btn--primary rv-focus flex-1"
                  :disabled="runningSource === source.id"
                  @click="runSourceJob(source, 'import_missing_files')"
                >
                  <Loader v-if="runningSource === source.id" class="size-4 animate-spin" />
                  <Play v-else class="size-4" />
                  ورود
                </button>
              </div>
            </div>
          </li>
        </ul>
      </RvPanel>
    </template>

    <template v-else>
      <!-- Bulk: catalog year import -->
      <RvPanel :icon="Layers" title="ایمپورت گروهی کاتالوگ" subtitle="کشف عنوان‌های تازه از همه ارائه‌دهنده‌ها با پنجره سال">
        <div class="grid gap-3 sm:grid-cols-3">
          <label class="block">
            <span class="rv-label">نوع محتوا</span>
            <select v-model="yearForm.content_type" class="rv-input mt-1.5">
              <option value="movies">فیلم</option>
              <option value="series">سریال</option>
              <option value="both">هر دو</option>
            </select>
          </label>
          <label class="block">
            <span class="rv-label">از سال (خالی = همه)</span>
            <input v-model="yearForm.year_start" type="number" min="1900" max="2100" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">تا سال (خالی = همه)</span>
            <input v-model="yearForm.year_end" type="number" min="1900" max="2100" dir="ltr" class="rv-input mt-1.5">
          </label>
        </div>
        <div class="mt-3 flex flex-wrap gap-4">
          <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
            <input v-model="yearForm.providers" type="checkbox" value="dornatv" class="rv-focus size-4 accent-[var(--rv-accent)]">
            دورنا تی‌وی
          </label>
          <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
            <input v-model="yearForm.providers" type="checkbox" value="myf2m" class="rv-focus size-4 accent-[var(--rv-accent)]">
            فیلم‌تومدیا
          </label>
          <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
            <input v-model="yearForm.discover" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
            کشف
          </label>
          <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
            <input v-model="yearForm.enrich" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
            غنی‌سازی
          </label>
          <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
            <input v-model="yearForm.softsub" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
            صف زیرنویس
          </label>
        </div>
        <details class="mt-3 rounded-[var(--rv-radius-sm)] border border-[var(--rv-border)]">
          <summary class="rv-focus cursor-pointer px-3 py-2.5 text-xs font-black text-[var(--rv-muted)]">تنظیمات پیشرفته دورها</summary>
          <div class="grid gap-3 border-t border-[var(--rv-border)] p-3 sm:grid-cols-3">
            <label class="block">
              <span class="rv-label">دور دورنا</span>
              <input v-model.number="yearForm.dornatv_rounds" type="number" min="1" max="50" dir="ltr" class="rv-input mt-1.5">
            </label>
            <label class="block">
              <span class="rv-label">فیلم/دور دورنا</span>
              <input v-model.number="yearForm.movies_per_round" type="number" min="1" max="500" dir="ltr" class="rv-input mt-1.5">
            </label>
            <label class="block">
              <span class="rv-label">سریال/دور دورنا</span>
              <input v-model.number="yearForm.series_per_round" type="number" min="1" max="250" dir="ltr" class="rv-input mt-1.5">
            </label>
            <label class="block">
              <span class="rv-label">دور myf2m</span>
              <input v-model.number="yearForm.myf2m_rounds" type="number" min="1" max="50" dir="ltr" class="rv-input mt-1.5">
            </label>
            <label class="block">
              <span class="rv-label">فیلم/دور myf2m</span>
              <input v-model.number="yearForm.myf2m_movies_per_round" type="number" min="1" max="500" dir="ltr" class="rv-input mt-1.5">
            </label>
            <label class="block">
              <span class="rv-label">سریال/دور myf2m</span>
              <input v-model.number="yearForm.myf2m_series_per_round" type="number" min="1" max="250" dir="ltr" class="rv-input mt-1.5">
            </label>
          </div>
        </details>
        <button
          type="button"
          class="rv-btn rv-btn--primary rv-focus mt-4 w-full"
          :disabled="startingYearImport || !yearForm.providers.length"
          @click="startYearImport"
        >
          <Loader v-if="startingYearImport" class="size-4 animate-spin" />
          <Play v-else class="size-4" />
          شروع ایمپورت گروهی
        </button>
      </RvPanel>

      <!-- Bulk: TMDB sync runs -->
      <RvPanel :icon="RefreshCw" title="هم‌گام‌سازی TMDB" subtitle="ورود خودکار متادیتا از TMDB">
        <template #actions>
          <button type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs" @click="loadSyncRuns()">
            تازه‌سازی
          </button>
        </template>

        <form class="flex flex-wrap items-end gap-3" @submit.prevent="startSyncRun">
          <label class="block min-w-[140px]">
            <span class="rv-label">حالت</span>
            <select v-model="syncForm.mode" class="rv-input mt-1.5">
              <option v-for="o in SYNC_MODES" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <template v-if="syncForm.mode === 'daily' || syncForm.mode === 'incremental'">
            <label class="block w-28">
              <span class="rv-label">روز گذشته</span>
              <input v-model.number="syncForm.lookback_days" type="number" min="1" max="14" dir="ltr" class="rv-input mt-1.5">
            </label>
            <label class="block w-28">
              <span class="rv-label">روز آینده</span>
              <input v-model.number="syncForm.lookahead_days" type="number" min="0" max="90" dir="ltr" class="rv-input mt-1.5">
            </label>
          </template>
          <label v-if="syncForm.mode !== 'full'" class="block w-28">
            <span class="rv-label">سقف صفحه</span>
            <input v-model.number="syncForm.max_pages" type="number" min="1" max="500" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label v-if="syncForm.mode === 'trending'" class="block min-w-[120px]">
            <span class="rv-label">بازه</span>
            <select v-model="syncForm.window" class="rv-input mt-1.5">
              <option value="day">روز</option>
              <option value="week">هفته</option>
            </select>
          </label>
          <label v-if="syncForm.mode === 'full'" class="flex items-center gap-2 pb-2.5 text-xs font-bold text-[var(--rv-danger)]">
            <input v-model="syncForm.confirm_full" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
            ایمپورت کامل را تأیید می‌کنم
          </label>
          <button type="submit" class="rv-btn rv-btn--ghost rv-focus" :disabled="syncStarting || (syncForm.mode === 'full' && !syncForm.confirm_full)">
            <Loader v-if="syncStarting" class="size-4 animate-spin" />
            <Play v-else class="size-4" />
            شروع
          </button>
        </form>

        <RvState v-if="syncRunsError" kind="error" title="فهرست اجراها خوانده نشد" @retry="loadSyncRuns()" />
        <ul v-else-if="syncRuns.length" class="mt-3 divide-y divide-[var(--rv-border)]">
          <li v-for="run in syncRuns" :key="run.id" class="flex flex-wrap items-center gap-2.5 py-2.5 first:pt-0 last:pb-0">
            <RvBadge :tone="SYNC_STATUS_TONE[run.status] || 'neutral'" dot>
              {{ SYNC_STATUS_LABEL[run.status] || run.status }}
            </RvBadge>
            <span class="min-w-0 flex-1 text-xs font-bold text-[var(--rv-text)]">
              {{ run.mode }}
              <span class="text-[var(--rv-muted)]"> · {{ fa(run.processed_count) }}/{{ fa(run.total_count) }} · {{ fa(run.progress_percent) }}٪</span>
            </span>
            <button
              v-if="run.can_cancel"
              type="button"
              class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
              :disabled="syncCancelling === run.id"
              @click="cancelSyncRun(run)"
            >
              <Loader v-if="syncCancelling === run.id" class="size-3.5 animate-spin" />
              <Square v-else class="size-3.5" />
              لغو
            </button>
          </li>
        </ul>
        <p v-else class="mt-3 text-xs font-semibold text-[var(--rv-muted)]">هنوز اجرایی ثبت نشده است.</p>
      </RvPanel>

      <!-- Bulk: importer settings -->
      <RvPanel :icon="Settings" title="تنظیمات ایمپورتر" subtitle="زبان، منطقه و سقف‌های ورود خودکار TMDB">
        <RvState v-if="bulkLoaded && !importerSettings" title="تنظیمات خوانده نشد" message="دوباره تلاش کنید." @retry="loadImporterSettings()" />
        <div v-else-if="importerSettings" class="grid gap-3 sm:grid-cols-3">
          <label class="block">
            <span class="rv-label">زبان</span>
            <input v-model="importerSettings.language" type="text" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">زبان جایگزین</span>
            <input v-model="importerSettings.fallback_language" type="text" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">منطقه</span>
            <input v-model="importerSettings.region" type="text" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">روز گذشته روزانه</span>
            <input v-model.number="importerSettings.daily_lookback_days" type="number" min="1" max="14" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">روز آینده روزانه</span>
            <input v-model.number="importerSettings.daily_lookahead_days" type="number" min="0" max="90" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">سقف صفحه روزانه</span>
            <input v-model.number="importerSettings.daily_max_pages" type="number" min="1" max="500" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">بازه ترند</span>
            <select v-model="importerSettings.trending_window" class="rv-input mt-1.5">
              <option value="day">روز</option>
              <option value="week">هفته</option>
            </select>
          </label>
          <label class="block">
            <span class="rv-label">سقف صفحه ترند</span>
            <input v-model.number="importerSettings.trending_max_pages" type="number" min="1" max="20" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">سقف عوامل</span>
            <input v-model.number="importerSettings.cast_import_limit" type="number" min="0" max="100" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">فاصله خودکار (ساعت)</span>
            <input v-model.number="importerSettings.automation_interval_hours" type="number" min="1" max="168" dir="ltr" class="rv-input mt-1.5">
          </label>
          <label class="block">
            <span class="rv-label">حالت خودکار</span>
            <select v-model="importerSettings.automation_mode" class="rv-input mt-1.5">
              <option value="daily">روزانه</option>
              <option value="trending">ترندها</option>
            </select>
          </label>
          <div class="flex flex-wrap gap-x-6 gap-y-3 sm:col-span-2">
            <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
              <input v-model="importerSettings.import_people_images" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              تصاویر عوامل
            </label>
            <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
              <input v-model="importerSettings.fetch_imdb_ratings" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              امتیاز IMDb
            </label>
            <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
              <input v-model="importerSettings.feature_trending" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              ویژه‌سازی ترندها
            </label>
            <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
              <input v-model="importerSettings.auto_publish" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              انتشار خودکار
            </label>
            <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
              <input v-model="importerSettings.automation_enabled" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
              خودکارسازی فعال
            </label>
          </div>
          <div class="sm:col-span-3">
            <button type="button" class="rv-btn rv-btn--primary rv-focus w-full" :disabled="settingsSaving" @click="saveImporterSettings">
              <Loader v-if="settingsSaving" class="size-4 animate-spin" />
              <Check v-else class="size-4" />
              ذخیره تنظیمات
            </button>
          </div>
        </div>
      </RvPanel>
    </template>

    <!-- Jobs -->
    <RvPanel :icon="Radar" title="اجراهای خزنده" subtitle="آخرین جستجوهای لینک پخش و ایمپورت‌ها">
      <template #actions>
        <RvBadge v-if="hasLiveJob" tone="info" dot>در حال اجرا</RvBadge>
        <button type="button" class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs" @click="loadJobs()">
          تازه‌سازی
        </button>
      </template>

      <RvState v-if="jobsError" kind="error" title="فهرست اجراها خوانده نشد" @retry="loadJobs()" />
      <RvState v-else-if="!jobs.length" title="هنوز اجرایی ثبت نشده" message="پس از ورود یک عنوان، «یافتن لینک پخش» را بزنید." />
      <ul v-else class="divide-y divide-[var(--rv-border)]">
        <li v-for="job in jobs" :key="job.id" class="flex flex-wrap items-center gap-2.5 py-2.5 first:pt-0 last:pb-0">
          <RvBadge :tone="JOB_TONE[String(job.status)] || 'neutral'" dot>
            {{ JOB_LABEL[String(job.status)] || job.status }}
          </RvBadge>
          <span class="min-w-0 flex-1 truncate text-xs font-bold text-[var(--rv-text)]">
            {{ job.provider_name || jobTarget(job) }}
            <span v-if="job.provider_name && (job.target_movie || job.target_series || job.object_id)" class="text-[var(--rv-muted)]">
              · {{ jobTarget(job) }}
            </span>
            <span v-if="job.current_item_label" class="block truncate text-xs font-semibold text-[var(--rv-faint)]">
              {{ job.current_item_label }}
            </span>
          </span>
          <span class="text-xs font-bold text-[var(--rv-muted)]">
            {{ fa(job.processed_items ?? 0) }}/{{ fa(job.total_items ?? 0) }}
            <span v-if="jobImported(job)"> · {{ fa(jobImported(job)) }} افزوده</span>
          </span>
          <button
            v-if="LIVE_JOB_STATUSES.includes(job.status)"
            type="button"
            class="rv-btn rv-btn--ghost rv-focus !min-h-8 !px-2.5 !text-xs"
            :disabled="cancellingJob === job.id"
            @click="cancelJob(job)"
          >
            <Loader v-if="cancellingJob === job.id" class="size-3.5 animate-spin" />
            <Square v-else class="size-3.5" />
            لغو
          </button>
          <span v-if="job.error_message" class="w-full truncate text-xs font-semibold text-[var(--rv-danger)]">
            {{ job.error_message }}
          </span>
        </li>
      </ul>
    </RvPanel>

    <!-- Preview / import drawer -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-200"
        enter-from-class="opacity-0"
        leave-active-class="transition duration-150"
        leave-to-class="opacity-0"
      >
        <div
          v-if="selected"
          class="fixed inset-0 z-[60] grid place-items-end bg-black/60 backdrop-blur-sm sm:place-items-center"
          role="dialog"
          aria-modal="true"
          @click.self="closePreview"
        >
          <div class="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-[var(--rv-surface)] p-5 sm:max-w-2xl sm:rounded-2xl">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="truncate text-base font-black text-[var(--rv-text)]">{{ selected.title }}</h2>
                <p class="mt-0.5 text-xs font-bold text-[var(--rv-muted)]">
                  {{ selected.kind === 'series' ? 'سریال' : 'فیلم' }}
                  <span v-if="yearOf(selected)"> · {{ yearOf(selected) }}</span>
                  · TMDB {{ selected.tmdb_id }}
                </p>
              </div>
              <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9 !px-2.5" aria-label="بستن" @click="closePreview">
                <X class="size-4" />
              </button>
            </div>

            <div v-if="previewing" class="mt-4 h-32 animate-pulse rounded-[var(--rv-radius-sm)] bg-[var(--rv-surface-3)]" />

            <template v-else>
              <div class="mt-4 flex gap-4">
                <img
                  v-if="preview?.poster_url || selected.poster_url"
                  :src="preview?.poster_url || selected.poster_url || ''"
                  :alt="selected.title"
                  class="h-40 w-[108px] shrink-0 rounded-[var(--rv-radius-sm)] object-cover"
                >
                <div class="min-w-0 flex-1 space-y-2">
                  <p class="line-clamp-6 text-xs leading-6 text-[var(--rv-muted)]">
                    {{ preview?.overview || selected.overview || 'خلاصه‌ای ثبت نشده است.' }}
                  </p>
                  <div class="flex flex-wrap gap-1.5">
                    <RvBadge v-if="preview?.imdb_rating" tone="warning">IMDb {{ preview.imdb_rating }}</RvBadge>
                    <RvBadge v-if="preview?.runtime" tone="neutral">{{ fa(preview.runtime) }} دقیقه</RvBadge>
                    <RvBadge v-if="preview?.number_of_seasons" tone="neutral">{{ fa(preview.number_of_seasons) }} فصل</RvBadge>
                    <RvBadge v-if="preview?.number_of_episodes" tone="neutral">{{ fa(preview.number_of_episodes) }} قسمت</RvBadge>
                  </div>
                </div>
              </div>

              <!-- Step 1: metadata -->
              <div class="mt-5 rounded-[var(--rv-radius-sm)] border border-[var(--rv-border)] p-3">
                <p class="text-xs font-black text-[var(--rv-text)]">۱ — افزودن به کتابخانه</p>
                <div class="mt-2.5 flex flex-wrap gap-4">
                  <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
                    <input v-model="publishNow" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
                    انتشار فوری
                  </label>
                  <label class="flex items-center gap-2 text-xs font-bold text-[var(--rv-muted)]">
                    <input v-model="overwriteManual" type="checkbox" class="rv-focus size-4 accent-[var(--rv-accent)]">
                    بازنویسی ویرایش‌های دستی
                  </label>
                </div>
                <p v-if="publishNow" class="mt-2 text-xs font-semibold text-[var(--rv-warning)]">
                  هنوز لینک پخشی گرفته نشده؛ انتشار فوری یعنی عنوان بدون منبع روی سایت می‌رود.
                </p>
                <button
                  type="button"
                  class="rv-btn rv-btn--primary rv-focus mt-3 w-full"
                  :disabled="importing"
                  @click="runImport"
                >
                  <Loader v-if="importing" class="size-4 animate-spin" />
                  <DownloadCloud v-else class="size-4" />
                  {{ localItem ? 'به‌روزرسانی اطلاعات' : 'افزودن به کتابخانه' }}
                </button>
              </div>

              <!-- Step 2: sources -->
              <div
                class="mt-3 rounded-[var(--rv-radius-sm)] border p-3"
                :style="localItem
                  ? { borderColor: 'var(--rv-border)' }
                  : { borderColor: 'var(--rv-border)', opacity: '0.55' }"
              >
                <p class="text-xs font-black text-[var(--rv-text)]">۲ — یافتن لینک پخش</p>
                <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">
                  خزنده‌ها عنوان را روی سرویس‌دهنده‌ها پیدا می‌کنند و لینک‌ها پیش از ذخیره تست می‌شوند.
                </p>
                <button
                  type="button"
                  class="rv-btn rv-btn--ghost rv-focus mt-3 w-full"
                  :disabled="!localItem || discovering"
                  @click="discoverSources"
                >
                  <Loader v-if="discovering" class="size-4 animate-spin" />
                  <Radar v-else class="size-4" />
                  اجرای خزنده
                </button>
              </div>

              <div v-if="localItem" class="mt-3 flex flex-wrap gap-2">
                <NuxtLink :to="editLinkFor(selected, localItem)" class="rv-btn rv-btn--subtle rv-focus flex-1">
                  <Pencil class="size-4" /> ویرایش
                </NuxtLink>
                <a
                  v-if="localItem.slug"
                  :href="`/${selected.kind === 'series' ? 'series' : 'movies'}/${localItem.slug}`"
                  target="_blank"
                  rel="noopener"
                  class="rv-btn rv-btn--subtle rv-focus flex-1"
                >
                  <ExternalLink class="size-4" /> مشاهده در سایت
                </a>
              </div>
              <p v-else class="mt-3 flex items-center gap-1.5 text-xs font-semibold text-[var(--rv-muted)]">
                <Check class="size-3.5" /> پس از افزودن، ویرایش و اجرای خزنده در دسترس می‌شود.
              </p>
            </template>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

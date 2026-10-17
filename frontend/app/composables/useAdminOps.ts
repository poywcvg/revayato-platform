import type {
  AdminContentKind,
  AuditFeedResponse,
  BulkResponse,
  DeskAction,
  DeskActionResponse,
  HealthQueue,
  HealthResponse,
  MediaDesk,
  OpsOverview,
} from '~/types/admin'

/**
 * One home for the operations desk: per-title media control, bulk verbs, the
 * health queues and the crawler overview.
 *
 * The desk is read and written through a single endpoint, and every write
 * answers with the *whole* refreshed desk. That is deliberate — an action like
 * «حذف لینک» changes the publish blockers, the diagnosis and possibly the
 * playback mode, so a component that patched only the row it touched would show
 * a title as playable seconds after making it unplayable.
 */
export function useAdminOps() {
  const { api } = useApi()

  const deskPath = (kind: AdminContentKind, id: number) =>
    `/admin/catalog/${kind === 'series' ? 'series' : 'movie'}/${id}/media/`

  function fetchDesk(kind: AdminContentKind, id: number) {
    return api<MediaDesk>(deskPath(kind, id))
  }

  function runAction(
    kind: AdminContentKind,
    id: number,
    action: DeskAction,
    payload: Record<string, unknown> = {},
  ) {
    return api<DeskActionResponse>(deskPath(kind, id), {
      method: 'POST',
      body: { action, ...payload },
      // Verification and TMDB sync make network calls inside the request; the
      // shared 10s API ceiling would abort them mid-probe and tell the admin
      // nothing happened while it actually did.
      timeout: 60_000,
    })
  }

  function bulk(
    kind: AdminContentKind,
    ids: number[],
    action: string,
    payload: Record<string, unknown> = {},
  ) {
    return api<BulkResponse>('/admin/catalog/bulk/', {
      method: 'POST',
      body: { kind, ids, action, ...payload },
      // The backend stops a batch at 70s and reports the rest as time_budget;
      // Cloudflare cuts the connection at 100s. Stay between the two.
      timeout: 95_000,
    })
  }

  function health(queue: HealthQueue, query: Record<string, unknown> = {}) {
    return api<HealthResponse>('/admin/catalog/health/', { query: { queue, ...query } })
  }

  function opsOverview() {
    return api<OpsOverview>('/admin/ops/overview/', { timeout: 30_000 })
  }

  function auditFeed(query: Record<string, unknown> = {}) {
    return api<AuditFeedResponse>('/admin/audit/', { query })
  }

  return { fetchDesk, runAction, bulk, health, opsOverview, auditFeed }
}

/** Persian labels for everything the desk reports, in one place. */
export const LINK_HEALTH_LABEL: Record<string, string> = {
  live: 'سالم',
  dead: 'مرده',
  unknown: 'نامعلوم',
  unchecked: 'تست نشده',
}

export const LINK_HEALTH_TONE: Record<string, 'success' | 'danger' | 'warning' | 'neutral'> = {
  live: 'success',
  dead: 'danger',
  unknown: 'warning',
  unchecked: 'neutral',
}

/** Why the identity guard rejected a link — the reason staff needs to judge it. */
export const INTEGRITY_LABEL: Record<string, string> = {
  A_series: 'لینک یک سریال است، نه این فیلم',
  B_wrongfilm: 'متعلق به فیلم دیگری است',
  seq_diff: 'قسمت دیگری از همین مجموعه است',
  remake: 'بازسازی/نسخهٔ دیگر همین عنوان',
  same_title_yeardiff: 'همنام ولی سال متفاوت',
  C_offby1: 'سال یک واحد اختلاف دارد',
  B_partial: 'تطابق ناقص نام',
  ok: 'مطابق',
  unknown: 'قابل تشخیص نیست',
}

export const GAP_STATUS_LABEL: Record<string, string> = {
  open: 'باز',
  queued: 'در صف',
  remediating: 'در حال ترمیم',
  resolved: 'حل شده',
  needs_review: 'نیاز به بررسی',
  rejected: 'رد شده',
  unavailable: 'در دسترس نیست',
  exhausted: 'تلاش‌ها تمام شد',
}

export const BLOCKER_LABEL: Record<string, string> = {
  title_fa: 'عنوان فارسی',
  title_en: 'عنوان انگلیسی',
  original_title: 'عنوان اصلی',
  description: 'خلاصهٔ داستان',
  poster: 'پوستر',
  backdrop: 'تصویر پس‌زمینه',
  imdb_rating: 'امتیاز IMDb',
  release_year: 'سال انتشار',
  genres: 'ژانر',
  cast: 'بازیگران',
  directors: 'کارگردان',
  age_rating: 'ردهٔ سنی',
  trailer: 'تریلر',
  duration: 'مدت زمان',
  no_playable_source: 'هیچ منبع قابل پخشی ندارد',
  media_unverified: 'منابع تأیید نشده‌اند',
  media_failed: 'تست منابع شکست خورد',
  no_download_links: 'هیچ لینکی ندارد',
  no_episodes: 'هیچ قسمتی ندارد',
  // Gap codes exactly as the publish gate (completeness.py) reports them.
  missing_title: 'عنوان',
  missing_persian_title: 'عنوان فارسی',
  missing_english_title: 'عنوان انگلیسی',
  non_latin_english_title: 'عنوان انگلیسی با حروف لاتین نیست',
  missing_description: 'خلاصهٔ داستان',
  missing_persian_description: 'خلاصهٔ داستان فارسی',
  missing_short_description: 'خلاصهٔ کوتاه',
  missing_cast: 'بازیگران',
  missing_genres: 'ژانر',
  missing_directors: 'کارگردان',
  missing_poster: 'پوستر',
  missing_backdrop: 'تصویر پس‌زمینه',
  missing_imdb_rating: 'امتیاز IMDb',
  missing_rating: 'امتیاز',
  missing_release_year: 'سال انتشار',
  media_sources_dead: 'هیچ لینک سالمی پیدا نشد',
}

/** Falls back to the raw key so a new backend blocker is never swallowed. */
export function blockerLabel(key: string) {
  return BLOCKER_LABEL[key] || key
}

/** Refusal codes the admin endpoints answer with, in words an admin can act on. */
const ADMIN_ERROR_CODE: Record<string, string> = {
  contaminated_link: 'این لینک متعلق به عنوان دیگری است',
  link_rejected_by_normalizer: 'لینک پذیرفته نشد (میزبان مرده یا پسوند نامعتبر)',
  publish_blocked: 'برای انتشار کامل نیست',
  queue_failed: 'صف پردازش در دسترس نبود؛ کمی بعد دوباره امتحان کنید',
  action_failed: 'اجرای عملیات روی سرور با خطا تمام شد',
  duplicate_link: 'این لینک از قبل ثبت شده است',
  link_not_found: 'این لینک دیگر در فهرست نیست؛ صفحه را تازه کنید',
  selection_too_large: 'تعداد انتخاب‌ها برای این عملیات زیاد است',
  time_budget: 'به‌خاطر محدودیت زمان انجام نشد؛ دوباره اجرا کنید',
  not_found: 'این عنوان پیدا نشد',
  subtitle_worker_needs_published_title: 'زیرنویس فقط برای عنوان منتشرشده جستجو می‌شود',
}

/** Persian text for one refusal code (plus its blockers), for per-row bulk results. */
export function adminErrorCodeLabel(code?: string | null, blockers?: string[] | null) {
  const head = (code && ADMIN_ERROR_CODE[code]) || code || 'انجام نشد'
  const tail = (blockers || []).map(blockerLabel).join('، ')
  return tail ? `${head}: ${tail}` : head
}

function firstFieldError(data: Record<string, unknown>): string {
  for (const [field, value] of Object.entries(data)) {
    if (['detail', 'code', 'action', 'blockers'].includes(field)) continue
    const message = Array.isArray(value) ? value[0] : value
    if (typeof message === 'string' && message) return message
    if (message && typeof message === 'object') {
      const nested = firstFieldError(message as Record<string, unknown>)
      if (nested) return nested
    }
  }
  return ''
}

/**
 * Why an admin request failed, as one line. Every admin page used to say only
 * «عملیات ناموفق بود», which hid a throttle, a timeout, a validation message
 * and a publish gate behind the same words — so every failure looked like the
 * same unfixable bug.
 */
export function adminErrorMessage(error: unknown, fallback = 'عملیات ناموفق بود'): string {
  const err = error as {
    status?: number, statusCode?: number, name?: string, message?: string,
    data?: unknown, response?: { status?: number, headers?: Headers },
  }
  const status = err?.status || err?.statusCode || err?.response?.status || 0
  const data = (err?.data && typeof err.data === 'object') ? err.data as Record<string, unknown> : null

  if (!status) {
    const text = `${err?.name || ''} ${err?.message || ''}`
    if (/timeout|abort/i.test(text)) {
      return 'پاسخ سرور بیش از حد طول کشید؛ ممکن است عملیات انجام شده باشد — صفحه را تازه کنید'
    }
    return 'ارتباط با سرور برقرار نشد؛ اتصال اینترنت را بررسی کنید'
  }
  if (status === 429) {
    const wait = Number(err?.response?.headers?.get?.('Retry-After')) || 0
    return wait
      ? `درخواست‌ها زیاد بود؛ ${wait} ثانیه دیگر دوباره امتحان کنید`
      : 'درخواست‌ها زیاد بود؛ چند ثانیه دیگر دوباره امتحان کنید'
  }
  if (status === 401) return 'نشست شما تمام شده؛ دوباره وارد شوید'
  if (status === 403) return 'دسترسی مدیریت برای این حساب فعال نیست'
  if (status === 404) return 'این عنوان پیدا نشد (شاید حذف یا ادغام شده باشد)'
  if (status === 502 || status === 504 || status === 524) {
    if (data?.code) return adminErrorCodeLabel(String(data.code))
    return 'سرور در زمان مقرر پاسخ نداد؛ ممکن است عملیات انجام شده باشد — صفحه را تازه کنید'
  }
  if (data) {
    const code = typeof data.code === 'string' ? data.code : ''
    const blockers = Array.isArray(data.blockers) ? data.blockers as string[] : []
    if (code && (ADMIN_ERROR_CODE[code] || blockers.length)) return adminErrorCodeLabel(code, blockers)
    if (typeof data.detail === 'string' && data.detail) return data.detail
    if (typeof data.error === 'string' && data.error) return data.error
    const field = firstFieldError(data)
    if (field) return field
    if (code) return adminErrorCodeLabel(code)
  }
  if (status >= 500) return 'خطای داخلی سرور؛ جزئیات در لاگ ثبت شد'
  return fallback
}

/**
 * Crawler job vocabulary, shared by the import console and the operations page.
 *
 * Two pages showing the same job with different words for its state is how an
 * admin ends up believing they are looking at two different jobs.
 */
export const JOB_STATUS_LABEL: Record<string, string> = {
  completed: 'موفق',
  partially_completed: 'ناقص',
  failed: 'ناموفق',
  blocked: 'مسدود',
  cancelled: 'لغو شده',
  running: 'در حال اجرا',
  transferring: 'در حال انتقال',
  searching: 'در حال جستجو',
  validating: 'اعتبارسنجی',
  queued: 'در صف',
  awaiting_review: 'منتظر تأیید',
  cancel_requested: 'درخواست لغو',
}

export const JOB_STATUS_TONE: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
  completed: 'success',
  partially_completed: 'warning',
  failed: 'danger',
  blocked: 'danger',
  cancelled: 'neutral',
  running: 'info',
  transferring: 'info',
  searching: 'info',
  validating: 'info',
  queued: 'info',
  awaiting_review: 'warning',
  cancel_requested: 'warning',
}

export const SYNC_RUN_LABEL: Record<string, string> = {
  queued: 'در صف',
  running: 'در حال اجرا',
  cancelling: 'در حال لغو',
  cancelled: 'لغو شده',
  succeeded: 'موفق',
  failed: 'ناموفق',
}

export const SYNC_RUN_TONE: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
  queued: 'info',
  running: 'info',
  cancelling: 'warning',
  cancelled: 'neutral',
  succeeded: 'success',
  failed: 'danger',
}

/** What each Celery lane is for, in one line an admin can act on. */
export const QUEUE_LANE_HINT: Record<string, string> = {
  'celery': 'کارهای زمان‌بندی‌شده و نگهداری',
  'imports': 'خزش و ایمپورت محتوا',
  'softsub': 'استخراج زیرنویس انبوه',
  'softsub-urgent': 'زیرنویس فوری پلیر',
  'support': 'ترمیم خودکار گزارش‌ها',
}

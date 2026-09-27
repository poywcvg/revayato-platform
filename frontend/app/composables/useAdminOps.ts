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
      timeout: 120_000,
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
}

/** Falls back to the raw key so a new backend blocker is never swallowed. */
export function blockerLabel(key: string) {
  return BLOCKER_LABEL[key] || key
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

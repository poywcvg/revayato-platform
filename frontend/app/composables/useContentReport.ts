/** The «گزارش خطا» buttons, and the call that files one.
 *
 *  Each button names one symptom because one *distinct* repair addresses it on
 *  the server — the catalogue is defined in `apps/catalog/report_catalog.py` and
 *  served from `/api/catalog/report-issue/options/`, so shipping a new repair
 *  ships a new button without a frontend release.
 *
 *  The list below is a bundled copy of that catalogue, used for first paint and
 *  when the options call fails; the server's answer replaces it as soon as it
 *  lands. Keep the two in step — the server is the one that decides.
 */

import type { ContentType } from '~/types'

export type ReportProblemType =
  | 'playback'
  | 'buffering'
  | 'audio_silent'
  | 'audio_desync'
  | 'subtitle_missing'
  | 'subtitle_sync'
  | 'subtitle_garbled'
  | 'wrong_title'
  | 'wrong_episode'
  | 'quality'
  | 'download_dead'
  | 'other'

export interface ReportOption {
  value: ReportProblemType
  group: string
  label: string
  hint: string
  icon: string
  scope: 'both' | 'movie' | 'series'
  requires_episode?: boolean
  auto: boolean
}

export interface ReportOptionGroup {
  key: string
  label: string
  options: ReportOption[]
}

const GROUP_LABELS: Array<[string, string]> = [
  ['playback', 'پخش'],
  ['audio', 'صدا'],
  ['subtitle', 'زیرنویس'],
  ['content', 'محتوا'],
  ['download', 'دانلود'],
  ['other', 'موارد دیگر'],
]

const BUNDLED_OPTIONS: ReportOption[] = [
  { value: 'playback', group: 'playback', label: 'اصلاً پخش نمی‌شود', hint: 'ویدیو باز نمی‌شود یا خطا می‌دهد', icon: 'alert-triangle', scope: 'both', auto: true },
  { value: 'buffering', group: 'playback', label: 'مدام قطع و وصل می‌شود', hint: 'پخش شروع می‌شود ولی مدام می‌ایستد', icon: 'loader', scope: 'both', auto: true },
  { value: 'audio_silent', group: 'audio', label: 'تصویر هست، صدا نیست', hint: 'فیلم پخش می‌شود ولی هیچ صدایی ندارد', icon: 'volume-off', scope: 'both', auto: true },
  { value: 'audio_desync', group: 'audio', label: 'صدا با تصویر هماهنگ نیست', hint: 'صدا از تصویر جلو یا عقب است', icon: 'audio', scope: 'both', auto: true },
  { value: 'subtitle_missing', group: 'subtitle', label: 'زیرنویس ندارد', hint: 'هیچ زیرنویس فارسی‌ای در دسترس نیست', icon: 'captions-off', scope: 'both', auto: true },
  { value: 'subtitle_sync', group: 'subtitle', label: 'زیرنویس عقب یا جلو است', hint: 'متن با گفت‌وگو هم‌زمان نیست', icon: 'captions', scope: 'both', auto: true },
  { value: 'subtitle_garbled', group: 'subtitle', label: 'زیرنویس خراب یا نامفهوم است', hint: 'حروف به‌هم‌ریخته‌اند یا متن بی‌ربط است', icon: 'file-warning', scope: 'both', auto: true },
  { value: 'wrong_title', group: 'content', label: 'فیلم با عنوان صفحه فرق دارد', hint: 'چیزی که پخش می‌شود این فیلم نیست', icon: 'film', scope: 'both', auto: true },
  { value: 'wrong_episode', group: 'content', label: 'قسمت اشتباه است', hint: 'این ویدیو مربوط به قسمت دیگری است', icon: 'list-video', scope: 'series', requires_episode: true, auto: true },
  { value: 'quality', group: 'content', label: 'کیفیت تصویر خیلی پایین است', hint: 'تصویر تار است یا با کیفیت انتخابی نمی‌خواند', icon: 'gauge', scope: 'both', auto: true },
  { value: 'download_dead', group: 'download', label: 'لینک دانلود کار نمی‌کند', hint: 'دانلود شروع نمی‌شود یا نیمه‌کاره می‌ماند', icon: 'download', scope: 'both', auto: true },
  { value: 'other', group: 'other', label: 'مورد دیگر', hint: 'مشکلی که در این فهرست نیست', icon: 'info', scope: 'both', auto: false },
]

/** Bucket a flat option list into the display groups, dropping empty ones. */
export function groupReportOptions(options: ReportOption[]): ReportOptionGroup[] {
  return GROUP_LABELS
    .map(([key, label]) => ({ key, label, options: options.filter(option => option.group === key) }))
    .filter(group => group.options.length > 0)
}

/** The bundled buttons for one player, narrowed the same way the server does:
 *  «قسمت اشتباه» is meaningless for a film and unusable for a series whose
 *  player has not told us which episode is on screen. */
export function bundledReportOptions(contentType: ContentType | '' = '', hasEpisode = false): ReportOption[] {
  return BUNDLED_OPTIONS.filter((option) => {
    if (contentType && option.scope !== 'both' && option.scope !== contentType) return false
    if (option.requires_episode && !hasEpisode) return false
    return true
  })
}

// Fetched catalogues, keyed by the narrowing that produced them. Client-only:
// a module-level cache on the SSR server would be shared across requests.
const optionsCache = new Map<string, ReportOptionGroup[]>()

/** The buttons this player should show: bundled immediately, server-backed once
 *  `load()` resolves. A failed call is not an error — the bundled list stands. */
export function useReportOptions(
  contentType: MaybeRefOrGetter<ContentType | ''>,
  hasEpisode: MaybeRefOrGetter<boolean> = false,
) {
  const { api } = useApi()
  const fetched = ref<ReportOptionGroup[] | null>(null)

  const signature = computed(() => `${toValue(contentType) || ''}|${toValue(hasEpisode) ? 1 : 0}`)
  const groups = computed<ReportOptionGroup[]>(
    () => fetched.value ?? groupReportOptions(bundledReportOptions(toValue(contentType), toValue(hasEpisode))),
  )

  watch(signature, key => { fetched.value = optionsCache.get(key) ?? null })

  async function load() {
    if (!import.meta.client) return
    const key = signature.value
    const cached = optionsCache.get(key)
    if (cached) {
      fetched.value = cached
      return
    }
    try {
      const query = new URLSearchParams()
      const kind = toValue(contentType)
      if (kind) query.set('content_type', kind)
      if (toValue(hasEpisode)) query.set('episode_id', '1')
      const res = await api<{ groups?: ReportOptionGroup[] }>(
        `/catalog/report-issue/options/?${query.toString()}`, { timeout: 8_000 },
      )
      const groupsFromServer = (res?.groups || []).filter(group => group?.options?.length)
      if (!groupsFromServer.length) return
      optionsCache.set(key, groupsFromServer)
      if (signature.value === key) fetched.value = groupsFromServer
    }
    catch {
      // The bundled catalogue is a complete, working fallback.
    }
  }

  return { groups, load }
}

export interface ContentReportInput {
  type: ContentType
  objectId: number
  slug?: string
  episodeId?: number | null
  problemType: ReportProblemType
  version?: string
  sourceUrl?: string
  detail?: string
}

export interface ContentReportResult {
  ok: boolean
  reportId: number | null
  status: string
  problemType: string
  reportCount: number
  auto: boolean
  created: boolean
}

export function useContentReport() {
  const { api } = useApi()

  async function reportIssue(input: ContentReportInput): Promise<ContentReportResult | null> {
    const objectId = Number(input.objectId) || 0
    if (!objectId && !input.slug) return null
    if (!input.problemType) return null
    try {
      const res = await api<{
        ok?: boolean
        report_id?: number | null
        status?: string
        problem_type?: string
        report_count?: number
        auto?: boolean
        created?: boolean
      }>('/catalog/report-issue/', {
        method: 'POST',
        body: {
          content_type: input.type,
          problem_type: input.problemType,
          object_id: objectId,
          slug: input.slug || '',
          episode_id: input.type === 'series' ? input.episodeId || 0 : 0,
          playback_version: input.version || '',
          source_url: input.sourceUrl || '',
          detail: (input.detail || '').slice(0, 500),
        },
        timeout: 12_000,
      })
      return {
        ok: res?.ok !== false,
        reportId: res?.report_id ?? null,
        status: res?.status || 'open',
        problemType: res?.problem_type || input.problemType,
        reportCount: res?.report_count ?? 1,
        auto: Boolean(res?.auto),
        created: Boolean(res?.created),
      }
    } catch {
      // Best-effort: a failed report should never break playback for the viewer.
      return null
    }
  }

  async function readStatus(reportId: number) {
    if (!reportId) return null
    try {
      return await api(`/catalog/report-issue/status/?report_id=${encodeURIComponent(reportId)}`, {
        timeout: 8_000,
      })
    } catch {
      return null
    }
  }

  return { reportIssue, readStatus }
}

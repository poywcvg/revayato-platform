/**
 * «بازسازی تست‌شده» — the words the admin sees for a staged rebuild's outcome.
 *
 * The backend (apps/catalog/title_staging.py) rebuilds a title on a shadow
 * copy, probes it, and applies it only if it passes; every rejection carries a
 * reason code. This maps those codes, so the problem list and the title desk
 * say the same thing about the same run.
 */

export type RepairTone = 'success' | 'info' | 'warning' | 'danger' | 'neutral'

export const STAGED_REJECT_LABEL: Record<string, string> = {
  no_fresh_links: 'هیچ منبعی لینک تازه نداد',
  fresh_dead: 'لینک‌های تازه مرده بودند',
  fresh_mostly_dead: 'بیشتر لینک‌های تازه مرده بودند',
  test_inconclusive: 'میزبان‌ها به تست جواب ندادند',
  episode_coverage_drop: 'قسمت‌های کمتری از وضعیت فعلی داشت',
  apply_failed: 'اعمال با خطا متوقف شد',
  stage_failed: 'خزش منابع کامل نشد',
}

export interface RepairRun {
  mode?: string
  state?: string
  step?: string
  verdict?: string
  verdict_reason?: string
  finished_at?: string | null
  /** The problems that put the title on the health page, after the run. */
  problems_fixed?: string[]
  problems_queued?: string[]
  problems_left?: string[]
}

/** Same codes as apps/catalog/title_problems.py `LABELS`. */
export const PROBLEM_LABEL: Record<string, string> = {
  source_gap: 'پخش در مرورگر',
  sourceless: 'بدون لینک',
  failed_check: 'تست ناموفق',
  unverified: 'تأیید نشده',
  incomplete: 'اطلاعات ناقص',
  approx_rating: 'نمرهٔ تقریبی',
  subtitle_gap: 'زیرنویس',
  reports: 'گزارش کاربر',
}

/** «رفع شد: … · در صف: … · باقی مانده: …» — empty when the run predates the step. */
export function problemsLine(run: RepairRun | null | undefined): string {
  if (!run) return ''
  const names = (codes?: string[]) => (codes || []).map(code => PROBLEM_LABEL[code] || code).join('، ')
  return [
    run.problems_fixed?.length ? `رفع شد: ${names(run.problems_fixed)}` : '',
    run.problems_queued?.length ? `در صف: ${names(run.problems_queued)}` : '',
    run.problems_left?.length ? `باقی مانده: ${names(run.problems_left)}` : '',
  ].filter(Boolean).join(' · ')
}

const RUNNING_STEP: Record<string, string> = {
  metadata: 'اطلاعات',
  titles: 'عنوان',
  stage: 'خزش منابع',
  test: 'تست لینک‌ها',
  backup: 'پشتیبان',
  apply: 'جایگزینی',
  sources: 'خزش منابع',
  episodes: 'قسمت‌ها',
  playback: 'پخش آنلاین',
  sizes: 'اندازه‌ها',
  verify: 'تست نهایی',
  publish: 'انتشار',
  problems: 'رفع مشکل‌ها',
  subtitles: 'زیرنویس',
}

/** One badge for the last repair run on a title, or `null` when there is none. */
export function repairBadge(run: RepairRun | null | undefined): { label: string, tone: RepairTone, hint: string } | null {
  if (!run || !run.state) return null
  if (run.state === 'queued') return { label: 'در صف', tone: 'info', hint: '' }
  if (run.state === 'running') {
    const step = RUNNING_STEP[run.step || ''] || ''
    return { label: step ? `در حال اجرا · ${step}` : 'در حال اجرا', tone: 'info', hint: '' }
  }
  if (run.state === 'failed') return { label: 'متوقف شد', tone: 'danger', hint: 'اجرای پس‌زمینه کامل نشد' }
  const problems = problemsLine(run)
  // A problem still open turns a success into a warning: the row is not healed yet.
  const left = !!run.problems_left?.length
  if (run.mode === 'rebuild') {
    return {
      label: left ? 'جایگزین شد · مشکل باقی است' : 'جایگزین شد · بدون تست',
      tone: left ? 'warning' : 'success',
      hint: problems || 'نسخهٔ قبلی پشتیبان دارد',
    }
  }
  if (run.mode !== 'staged') return { label: 'تکمیل شد', tone: left ? 'warning' : 'neutral', hint: problems }
  if (run.verdict === 'applied') {
    return {
      label: left ? 'جایگزین شد · مشکل باقی است' : 'جایگزین شد',
      tone: left ? 'warning' : 'success',
      hint: problems || 'مجموعهٔ تازه تست شد و قرار گرفت',
    }
  }
  const reason = STAGED_REJECT_LABEL[run.verdict_reason || ''] || 'تست قبول نشد'
  return { label: 'دست نخورد', tone: 'warning', hint: problems ? `${reason} · ${problems}` : reason }
}

/** Whether any row is still moving, so the list keeps itself current. */
export function anyRepairActive(runs: (RepairRun | null | undefined)[]): boolean {
  return runs.some(run => run?.state === 'queued' || run?.state === 'running')
}

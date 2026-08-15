import type { AppErrorDetails, AppFieldError } from '~/types'

const FIELD_LABELS: Record<string, string> = {
  email: 'ایمیل',
  username: 'نام کاربری',
  login: 'ایمیل یا نام کاربری',
  password: 'رمز عبور',
  new_password: 'رمز عبور تازه',
  password_confirm: 'تکرار رمز عبور',
  first_name: 'نام',
  last_name: 'نام خانوادگی',
  phone: 'شماره موبایل',
  message: 'پیام',
  content_id: 'فیلم یا قسمت',
  invite_code: 'کد دعوت',
  title: 'عنوان',
  slug: 'اسلاگ',
  non_field_errors: 'اطلاعات واردشده',
  detail: 'جزئیات',
}

const COMMON_ENGLISH: Record<string, string> = {
  'this field is required.': 'پر کردن این بخش الزامی است.',
  'this field may not be blank.': 'این بخش نباید خالی باشد.',
  'a valid integer is required.': 'یک عدد صحیح وارد کن.',
  'enter a valid email address.': 'یک ایمیل معتبر وارد کن.',
  'invalid credentials': 'اطلاعات ورود درست نیست.',
  'authentication credentials were not provided.': 'برای این کار باید وارد حساب شوی.',
  'you do not have permission to perform this action.': 'اجازه انجام این کار را نداری.',
  'not found.': 'مورد درخواستی پیدا نشد.',
  'method not allowed.': 'این درخواست مجاز نیست.',
}

function statusOf(error: unknown) {
  if (!error || typeof error !== 'object') return 0
  const value = error as { status?: number; statusCode?: number; response?: { status?: number } }
  return value.status || value.statusCode || value.response?.status || 0
}

function dataOf(error: unknown): Record<string, unknown> {
  if (!error || typeof error !== 'object') return {}
  const value = error as { data?: unknown; response?: { _data?: unknown } }
  const data = value.data || value.response?._data
  return data && typeof data === 'object' && !Array.isArray(data) ? data as Record<string, unknown> : {}
}

function isPersian(value: string) {
  return /[\u0600-\u06ff]/.test(value)
}

function localizeMessage(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return ''
  if (isPersian(trimmed)) return trimmed
  const mapped = COMMON_ENGLISH[trimmed.toLowerCase()]
  if (mapped) return mapped
  // Keep short server messages so the user still sees a concrete reason.
  if (trimmed.length <= 220 && !/<[a-z][\s\S]*>/i.test(trimmed)) return trimmed
  return ''
}

function readable(value: unknown): string {
  if (typeof value === 'string') return localizeMessage(value)
  if (Array.isArray(value)) {
    return value
      .map(item => (typeof item === 'string' ? localizeMessage(item) : ''))
      .filter(Boolean)
      .join(' ')
  }
  if (value && typeof value === 'object') {
    const nested = Object.values(value as Record<string, unknown>)
      .map(item => readable(item))
      .filter(Boolean)
    return nested.join(' ')
  }
  return ''
}

function fieldsOf(data: Record<string, unknown>): AppFieldError[] {
  return Object.entries(data)
    .filter(([field]) => !['detail', 'hint', 'code', 'status_code', 'status'].includes(field))
    .map(([field, value]) => {
      const message = readable(value)
      return {
        field,
        label: FIELD_LABELS[field] || 'این بخش',
        message: message || 'مقدار این بخش درست نیست.',
      }
    })
    .filter(item => item.message)
}

const STATUS_COPY: Record<number, Pick<AppErrorDetails, 'title' | 'message' | 'hint'>> = {
  400: { title: 'اطلاعات نیاز به بررسی دارد', message: 'بعضی از اطلاعات واردشده درست نیست.', hint: 'موارد نوشته‌شده را اصلاح کن و دوباره تلاش کن.' },
  401: { title: 'ورود انجام نشد', message: 'اطلاعات ورود درست نیست یا زمان نشست تمام شده است.', hint: 'ایمیل و رمز عبور را بررسی کن و دوباره وارد شو.' },
  403: { title: 'اجازه این کار را نداری', message: 'حساب تو به این بخش دسترسی ندارد.', hint: 'اگر فکر می‌کنی اشتباهی رخ داده، با پشتیبانی تماس بگیر.' },
  404: { title: 'پیدا نشد', message: 'صفحه یا اطلاعاتی که خواستی پیدا نشد.', hint: 'آدرس را بررسی کن یا به صفحه قبل برگرد.' },
  409: { title: 'این مورد از قبل وجود دارد', message: 'امکان ثبت دوباره این اطلاعات نیست.', hint: 'اطلاعات دیگری وارد کن و دوباره تلاش کن.' },
  423: { title: 'ورود موقتاً بسته شده', message: 'به‌دلیل چند تلاش ناموفق، ورود این حساب برای مدت کوتاهی بسته است.', hint: 'کمی صبر کن یا رمز عبورت را بازیابی کن.' },
  429: { title: 'تلاش‌های زیادی انجام شد', message: 'برای امنیت حساب، درخواست‌ها موقتاً محدود شده‌اند.', hint: 'چند دقیقه صبر کن و دوباره تلاش کن.' },
  500: { title: 'مشکلی در سرور پیش آمد', message: 'درخواست تو این بار انجام نشد.', hint: 'کمی بعد دوباره تلاش کن؛ اطلاعاتت از بین نرفته است.' },
}

/** Build a single user-facing reason line from fields + hint. */
export function formatErrorReason(details: Pick<AppErrorDetails, 'fields' | 'hint' | 'message'>): string {
  const fieldLines = details.fields
    .map(item => `${item.label}: ${item.message}`)
    .filter(Boolean)
  if (fieldLines.length) return fieldLines.join(' · ')
  if (details.hint && details.hint !== details.message) return details.hint
  return ''
}

export function getAppError(error: unknown, fallback = 'انجام این کار ممکن نشد.'): AppErrorDetails {
  const status = statusOf(error)
  const data = dataOf(error)
  const preset = STATUS_COPY[status] || (status >= 500 ? STATUS_COPY[500] : undefined)
  const fields = fieldsOf(data)
  const detail = readable(data.detail)
  const hint = readable(data.hint) || preset?.hint

  if (!status && !(error instanceof Error && error.message)) {
    const offline: AppErrorDetails = {
      title: 'ارتباط با سایت برقرار نشد',
      message: 'اینترنت قطع است یا سرور پاسخ نمی‌دهد.',
      hint: 'اتصال اینترنت را بررسی کن و دوباره تلاش کن.',
      fields: [],
    }
    offline.reason = formatErrorReason(offline) || offline.hint
    return offline
  }

  // Network / thrown Error without HTTP status
  if (!status && error instanceof Error) {
    const network: AppErrorDetails = {
      title: 'ارتباط با سایت برقرار نشد',
      message: localizeMessage(error.message) || 'اینترنت قطع است یا سرور پاسخ نمی‌دهد.',
      hint: 'اتصال اینترنت را بررسی کن و دوباره تلاش کن.',
      fields: [],
    }
    network.reason = formatErrorReason(network) || network.message
    return network
  }

  const message = detail
    || (fields.length ? 'بعضی از اطلاعات واردشده نیاز به اصلاح دارد.' : preset?.message || fallback)

  const details: AppErrorDetails = {
    title: preset?.title || 'درخواست انجام نشد',
    message,
    hint,
    code: readable(data.code) || undefined,
    status,
    fields,
  }
  details.reason = formatErrorReason(details) || (detail && detail !== message ? detail : '') || details.hint || details.message
  return details
}

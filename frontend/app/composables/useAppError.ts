import type { AppErrorDetails, AppFieldError } from '~/types'

const FIELD_LABELS: Record<string, string> = {
  email: 'ایمیل',
  username: 'نام کاربری',
  password: 'رمز عبور',
  new_password: 'رمز عبور تازه',
  password_confirm: 'تکرار رمز عبور',
  message: 'پیام',
  content_id: 'فیلم یا قسمت',
  invite_code: 'کد دعوت',
  non_field_errors: 'اطلاعات واردشده',
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

function readable(value: unknown) {
  if (typeof value === 'string' && value.length <= 500 && !/<[a-z][\s\S]*>/i.test(value)) return value
  if (Array.isArray(value)) return value.filter(item => typeof item === 'string').join(' ')
  return ''
}

function isPersian(value: string) {
  return /[\u0600-\u06ff]/.test(value)
}

function fieldsOf(data: Record<string, unknown>): AppFieldError[] {
  return Object.entries(data)
    .filter(([field]) => !['detail', 'hint', 'code'].includes(field))
    .map(([field, value]) => ({
      field,
      label: FIELD_LABELS[field] || 'این بخش',
      message: isPersian(readable(value)) ? readable(value) : 'مقدار این بخش درست نیست.',
    }))
    .filter(item => item.message)
}

const STATUS_COPY: Record<number, Pick<AppErrorDetails, 'title' | 'message' | 'hint'>> = {
  400: { title: 'اطلاعات نیاز به بررسی دارد', message: 'بعضی از اطلاعات واردشده درست نیست.', hint: 'موارد نوشته‌شده زیر را اصلاح کن و دوباره تلاش کن.' },
  401: { title: 'ورود انجام نشد', message: 'اطلاعات ورود درست نیست یا زمان نشست تمام شده است.', hint: 'ایمیل و رمز عبور را بررسی کن و دوباره وارد شو.' },
  403: { title: 'اجازه این کار را نداری', message: 'حساب تو به این بخش دسترسی ندارد.', hint: 'اگر فکر می‌کنی اشتباهی رخ داده، با پشتیبانی تماس بگیر.' },
  404: { title: 'پیدا نشد', message: 'صفحه یا اطلاعاتی که خواستی پیدا نشد.', hint: 'آدرس را بررسی کن یا به صفحه قبل برگرد.' },
  409: { title: 'این مورد از قبل وجود دارد', message: 'امکان ثبت دوباره این اطلاعات نیست.', hint: 'اطلاعات دیگری وارد کن و دوباره تلاش کن.' },
  423: { title: 'ورود موقتاً بسته شده', message: 'به‌دلیل چند تلاش ناموفق، ورود این حساب برای مدت کوتاهی بسته است.', hint: 'کمی صبر کن یا رمز عبورت را بازیابی کن.' },
  429: { title: 'تلاش‌های زیادی انجام شد', message: 'برای امنیت حساب، درخواست‌ها موقتاً محدود شده‌اند.', hint: 'چند دقیقه صبر کن و دوباره تلاش کن.' },
  500: { title: 'مشکلی در سرور پیش آمد', message: 'درخواست تو این بار انجام نشد.', hint: 'کمی بعد دوباره تلاش کن؛ اطلاعاتت از بین نرفته است.' },
}

export function getAppError(error: unknown, fallback = 'انجام این کار ممکن نشد.'): AppErrorDetails {
  const status = statusOf(error)
  const data = dataOf(error)
  const preset = STATUS_COPY[status] || (status >= 500 ? STATUS_COPY[500] : undefined)
  const fields = fieldsOf(data)
  const rawDetail = readable(data.detail)
  const rawHint = readable(data.hint)
  const detail = isPersian(rawDetail) ? rawDetail : ''
  const hint = isPersian(rawHint) ? rawHint : ''

  if (!status) {
    return {
      title: 'ارتباط با سایت برقرار نشد',
      message: 'اینترنت قطع است یا سرور پاسخ نمی‌دهد.',
      hint: 'اتصال اینترنت را بررسی کن و دوباره تلاش کن.',
      fields: [],
    }
  }

  return {
    title: preset?.title || 'درخواست انجام نشد',
    message: detail || (fields.length ? 'بعضی از اطلاعات واردشده نیاز به اصلاح دارد.' : preset?.message || fallback),
    hint: hint || preset?.hint,
    code: readable(data.code) || undefined,
    status,
    fields,
  }
}

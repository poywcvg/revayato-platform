/** Cinematic toast metadata for online-player operational notices. */

import type { CinematicIconName } from '~/types'

export type PlayerToastTone = 'info' | 'success' | 'action' | 'warn' | 'network'

export interface PlayerToastMeta {
  tone: PlayerToastTone
  icon: CinematicIconName
  label?: string
}

export function classifyPlayerToast(message: string): PlayerToastMeta {
  const text = String(message || '').trim()
  const lower = text.toLowerCase()

  if (!text) return { tone: 'info', icon: 'info' }

  if (
    text.includes('زیرنویس فارسی فعال')
    || text.includes('زیرنویس آماده')
    || text.includes('کیفیت بهتر')
    || text.includes('شروع سریع')
    || text.includes('اتصال برقرار')
    || text.includes('تمام‌صفحه')
  ) {
    return { tone: 'success', icon: 'check', label: 'انجام شد' }
  }

  if (text.includes('زیرنویس') || text.includes('اندازه زیرنویس')) {
    if (text.includes('خاموش') || text.includes('نشد')) {
      return { tone: 'warn', icon: 'captions', label: 'زیرنویس' }
    }
    return { tone: 'action', icon: 'captions', label: 'زیرنویس' }
  }

  if (text.includes('دوبله') || text.includes('نسخه')) {
    return { tone: 'action', icon: 'audio', label: 'نسخه پخش' }
  }

  if (text.includes('کیفیت') || text.includes('خودکار')) {
    return { tone: 'action', icon: 'gauge', label: 'کیفیت' }
  }

  if (text.includes('سرعت')) {
    return { tone: 'action', icon: 'bolt', label: 'سرعت' }
  }

  if (text.includes('اینترنت') || text.includes('اتصال') || text.includes('آفلاین') || lower.includes('offline')) {
    return { tone: 'network', icon: 'signal-off', label: 'شبکه' }
  }

  if (text.includes('تیتراژ') || text.includes('پخش') || text.includes('روی صفحه')) {
    return { tone: 'info', icon: 'play', label: 'پخش' }
  }

  if (text.includes('تصویر در تصویر') || text.includes('تمام')) {
    return { tone: 'info', icon: 'maximize', label: 'نمایش' }
  }

  return { tone: 'info', icon: 'info' }
}

import { toast } from 'vue-sonner'
import type { AppErrorDetails, AppNotification, AppNotificationType } from '~/types'

const STORAGE_KEY = 'revayato:notifications:v1'
const MAX_NOTIFICATIONS = 30

export type NotifyOptions = {
  inbox?: boolean
  href?: string
  reason?: string
  duration?: number
}

function toastDescription(message: string, reason?: string) {
  if (!reason || reason === message) return message
  return `${message}\nدلیل: ${reason}`
}

export function useNotifications() {
  const notifications = useState<AppNotification[]>('app-notifications', () => [])
  const hydrated = useState('app-notifications-hydrated', () => false)
  const unreadCount = computed(() => notifications.value.filter(item => !item.read).length)

  function persist() {
    if (import.meta.client) localStorage.setItem(STORAGE_KEY, JSON.stringify(notifications.value.slice(0, MAX_NOTIFICATIONS)))
  }

  function hydrate() {
    if (!import.meta.client || hydrated.value) return
    hydrated.value = true
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
      if (Array.isArray(value)) notifications.value = value.slice(0, MAX_NOTIFICATIONS)
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }
  }

  function show(type: AppNotificationType, title: string, message: string, options: NotifyOptions = {}) {
    const reason = options.reason?.trim() || undefined
    const duration = options.duration ?? (type === 'error' ? (reason ? 8500 : 6500) : 4500)
    toast[type](title, {
      description: toastDescription(message, reason),
      duration,
    })
    if (options.inbox) {
      notifications.value = [{
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        type,
        title,
        message,
        reason,
        createdAt: new Date().toISOString(),
        read: false,
        href: options.href,
      }, ...notifications.value].slice(0, MAX_NOTIFICATIONS)
      persist()
    }
  }

  function success(title: string, message: string, options?: NotifyOptions) {
    show('success', title, message, options)
  }

  function error(title: string, message: string, options?: NotifyOptions) {
    show('error', title, message, { inbox: true, ...options })
  }

  function warning(title: string, message: string, options?: NotifyOptions) {
    show('warning', title, message, options)
  }

  function info(title: string, message: string, options?: NotifyOptions) {
    show('info', title, message, options)
  }

  /** Show an error toast (and inbox item) with a concrete user-facing reason. */
  function notifyError(cause: unknown, fallback = 'انجام این کار ممکن نشد.', options: NotifyOptions = {}) {
    const details = getAppError(cause, fallback)
    return notifyFromDetails(details, options)
  }

  function notifyFromDetails(details: AppErrorDetails, options: NotifyOptions = {}) {
    const reason = options.reason || details.reason || formatErrorReason(details) || details.hint || details.message
    error(details.title, details.message, {
      inbox: true,
      ...options,
      reason: reason === details.message ? (details.hint && details.hint !== details.message ? details.hint : reason) : reason,
    })
    return details
  }

  function markRead(id: string) {
    const item = notifications.value.find(value => value.id === id)
    if (item) {
      item.read = true
      persist()
    }
  }

  function markAllRead() {
    notifications.value.forEach(item => { item.read = true })
    persist()
  }

  function clear() {
    notifications.value = []
    persist()
  }

  return {
    notifications,
    unreadCount,
    hydrate,
    success,
    error,
    warning,
    info,
    notifyError,
    notifyFromDetails,
    markRead,
    markAllRead,
    clear,
  }
}

import { toast } from 'vue-sonner'
import type { AppNotification, AppNotificationType } from '~/types'

const STORAGE_KEY = 'revayato:notifications:v1'
const MAX_NOTIFICATIONS = 30

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

  function show(type: AppNotificationType, title: string, message: string, options: { inbox?: boolean; href?: string } = {}) {
    const toastOptions = { description: message, duration: type === 'error' ? 6500 : 4500 }
    toast[type](title, toastOptions)
    if (options.inbox) {
      notifications.value = [{
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        type,
        title,
        message,
        createdAt: new Date().toISOString(),
        read: false,
        href: options.href,
      }, ...notifications.value].slice(0, MAX_NOTIFICATIONS)
      persist()
    }
  }

  function success(title: string, message: string, options?: { inbox?: boolean; href?: string }) { show('success', title, message, options) }
  function error(title: string, message: string, options?: { inbox?: boolean; href?: string }) { show('error', title, message, options) }
  function warning(title: string, message: string, options?: { inbox?: boolean; href?: string }) { show('warning', title, message, options) }
  function info(title: string, message: string, options?: { inbox?: boolean; href?: string }) { show('info', title, message, options) }
  function markRead(id: string) { const item = notifications.value.find(value => value.id === id); if (item) { item.read = true; persist() } }
  function markAllRead() { notifications.value.forEach(item => { item.read = true }); persist() }
  function clear() { notifications.value = []; persist() }

  return { notifications, unreadCount, hydrate, success, error, warning, info, markRead, markAllRead, clear }
}

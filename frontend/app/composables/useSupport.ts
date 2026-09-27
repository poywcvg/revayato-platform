import type {
  CinematicIconName,
  SupportCategory,
  SupportStatus,
  SupportTicket,
  SupportTicketCreatePayload,
  SupportTicketListItem,
} from '~/types'

/** One source of truth for how a request status looks everywhere (client + admin). */
export const SUPPORT_STATUS_META: Record<SupportStatus, { label: string, tone: string, icon: CinematicIconName }> = {
  open: { label: 'باز', tone: 'sky', icon: 'info' },
  in_progress: { label: 'در حال بررسی', tone: 'amber', icon: 'refresh' },
  waiting_user: { label: 'منتظر پاسخ شما', tone: 'violet', icon: 'comment' },
  resolved: { label: 'حل‌شده', tone: 'emerald', icon: 'check-circle' },
  closed: { label: 'بسته', tone: 'zinc', icon: 'lock' },
}

export const SUPPORT_CATEGORY_META: Record<SupportCategory, { label: string, icon: CinematicIconName }> = {
  content_request: { label: 'درخواست عنوان', icon: 'film' },
  bug: { label: 'گزارش مشکل', icon: 'info' },
  content_fix: { label: 'اصلاح محتوا', icon: 'edit' },
  suggestion: { label: 'پیشنهاد', icon: 'sparkles' },
  support: { label: 'پشتیبانی', icon: 'comments' },
  cooperation: { label: 'همکاری', icon: 'heart' },
}

export function useSupport() {
  const { api } = useApi()

  function listMine() {
    return api<SupportTicketListItem[]>('/support/tickets/')
  }

  function create(payload: SupportTicketCreatePayload) {
    return api<SupportTicket>('/support/tickets/', { method: 'POST', body: payload })
  }

  function detail(trackingCode: string) {
    return api<SupportTicket>(`/support/tickets/${trackingCode}/`)
  }

  function reply(trackingCode: string, body: string) {
    return api<SupportTicket>(`/support/tickets/${trackingCode}/`, {
      method: 'POST',
      body: { body },
    })
  }

  return { listMine, create, detail, reply }
}

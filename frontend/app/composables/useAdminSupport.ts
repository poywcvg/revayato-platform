import type {
  AdminReviewItem,
  AdminReviewListResponse,
  AdminSupportInboxResponse,
  SupportStatus,
  SupportTicket,
} from '~/types'

export function useAdminSupport() {
  const { api } = useApi()

  function list(filters: {
    q?: string
    status?: string
    category?: string
    unread?: boolean
    limit?: number
    offset?: number
  } = {}) {
    return api<AdminSupportInboxResponse>('/admin/support/tickets/', {
      query: {
        q: filters.q || undefined,
        status: filters.status || undefined,
        category: filters.category || undefined,
        unread: filters.unread ? '1' : undefined,
        limit: filters.limit ?? 20,
        offset: filters.offset ?? 0,
      },
    })
  }

  function detail(trackingCode: string) {
    return api<SupportTicket>(`/admin/support/tickets/${trackingCode}/`)
  }

  function reply(trackingCode: string, body: string) {
    return api<SupportTicket>(`/admin/support/tickets/${trackingCode}/`, {
      method: 'POST',
      body: { body },
    })
  }

  function update(trackingCode: string, payload: { status?: SupportStatus; staff_note?: string; body?: string }) {
    return api<SupportTicket>(`/admin/support/tickets/${trackingCode}/`, {
      method: 'PATCH',
      body: payload,
    })
  }

  return { list, detail, reply, update }
}

export function useAdminReviews() {
  const { api } = useApi()

  function list(filters: {
    q?: string
    content_type?: string
    hidden?: '' | 'true' | 'false'
    limit?: number
    offset?: number
  } = {}) {
    return api<AdminReviewListResponse>('/admin/reviews/', {
      query: {
        q: filters.q || undefined,
        content_type: filters.content_type || undefined,
        hidden: filters.hidden || undefined,
        limit: filters.limit ?? 20,
        offset: filters.offset ?? 0,
      },
    })
  }

  function setHidden(id: number, isHidden: boolean) {
    return api<AdminReviewItem>(`/admin/reviews/${id}/`, {
      method: 'PATCH',
      body: { is_hidden: isHidden },
    })
  }

  return { list, setHidden }
}

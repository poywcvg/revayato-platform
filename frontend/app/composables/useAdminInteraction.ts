import type {
  AdminInteractionOverview,
  AdminReviewListResponse,
  AdminReviewItem,
  AdminSupportInboxResponse,
  AdminSupportTicket,
} from '~/types/admin'

/**
 * One home for every admin↔user interaction call (review moderation + support
 * inbox) plus the shared overview counts the admin shell shows as nav badges.
 */
export function useAdminInteraction() {
  const { api } = useApi()

  // Shared across the layout badge + each page so a reply/status change can
  // refresh the counters everywhere without prop drilling.
  const overview = useState<AdminInteractionOverview | null>('admin-interaction-overview', () => null)

  async function refreshOverview() {
    try {
      overview.value = await api<AdminInteractionOverview>('/admin/interaction-overview/')
    } catch {
      // A badge is a nicety; never let it break the shell.
    }
    return overview.value
  }

  // ----- Reviews ---------------------------------------------------------- //
  function listReviews(query: Record<string, unknown>) {
    return api<AdminReviewListResponse>('/admin/reviews/', { query })
  }

  function updateReview(id: number, payload: Record<string, unknown>) {
    return api<AdminReviewItem>(`/admin/reviews/${id}/`, { method: 'PATCH', body: payload })
  }

  // ----- Support ---------------------------------------------------------- //
  function listTickets(query: Record<string, unknown>) {
    return api<AdminSupportInboxResponse>('/admin/support/tickets/', { query })
  }

  function ticketDetail(trackingCode: string) {
    return api<AdminSupportTicket>(`/admin/support/tickets/${trackingCode}/`)
  }

  function replyTicket(trackingCode: string, body: string) {
    return api<AdminSupportTicket>(`/admin/support/tickets/${trackingCode}/`, {
      method: 'POST',
      body: { body },
    })
  }

  function patchTicket(trackingCode: string, payload: Record<string, unknown>) {
    return api<AdminSupportTicket>(`/admin/support/tickets/${trackingCode}/`, {
      method: 'PATCH',
      body: payload,
    })
  }

  return {
    overview,
    refreshOverview,
    listReviews,
    updateReview,
    listTickets,
    ticketDetail,
    replyTicket,
    patchTicket,
  }
}

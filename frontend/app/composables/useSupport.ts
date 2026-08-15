import type { SupportTicket, SupportTicketCreatePayload, SupportTicketListItem } from '~/types'

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

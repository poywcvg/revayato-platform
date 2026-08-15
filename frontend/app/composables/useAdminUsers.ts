import type { AdminUser, AdminUserFilters, AdminUserListResponse } from '~/types'

export function useAdminUsers() {
  const { api } = useApi()

  function list(filters: AdminUserFilters = {}) {
    return api<AdminUserListResponse>('/admin/users/', {
      query: {
        q: filters.q || undefined,
        role: filters.role || undefined,
        active: filters.active || undefined,
        limit: filters.limit ?? 20,
        offset: filters.offset ?? 0,
      },
    })
  }

  function detail(id: number) {
    return api<AdminUser>(`/admin/users/${id}/`)
  }

  function create(payload: {
    email: string
    username: string
    password: string
    first_name?: string
    last_name?: string
    phone?: string | null
    is_staff?: boolean
    is_active?: boolean
    is_verified?: boolean
  }) {
    return api<AdminUser>('/admin/users/', { method: 'POST', body: payload })
  }

  function update(id: number, payload: Partial<{
    email: string
    username: string
    first_name: string
    last_name: string
    phone: string | null
    is_active: boolean
    is_staff: boolean
    is_superuser: boolean
    is_verified: boolean
    password: string
  }>) {
    return api<AdminUser>(`/admin/users/${id}/`, { method: 'PATCH', body: payload })
  }

  return { list, detail, create, update }
}

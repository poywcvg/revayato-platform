<script setup lang="ts">
import type { AdminUser, AdminUserListResponse } from '~/types/admin'
import Users from '~icons/lucide/users-round'
import Search from '~icons/lucide/search'
import ShieldCheck from '~icons/lucide/shield-check'
import BadgeCheck from '~icons/lucide/badge-check'
import UserCheck from '~icons/lucide/user-check'
import UserX from '~icons/lucide/user-x'
import ChevronRight from '~icons/lucide/chevron-right'
import ChevronLeft from '~icons/lucide/chevron-left'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'مدیریت کاربران — روایتو' })

const { api } = useApi()
const notify = useNotifications()
const auth = useAuthStore()

const PAGE_SIZE = 20
const q = ref('')
const qDebounced = ref('')
const roleFilter = ref<'' | 'staff' | 'user'>('')
const activeFilter = ref<'' | 'true' | 'false'>('')
const offset = ref(0)

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(q, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { qDebounced.value = val.trim(); offset.value = 0 }, 350)
})
watch([roleFilter, activeFilter], () => { offset.value = 0 })

const ROLE_OPTIONS = [
  { value: '', label: 'همه نقش‌ها' },
  { value: 'staff', label: 'مدیران' },
  { value: 'user', label: 'کاربران عادی' },
]
const ACTIVE_OPTIONS = [
  { value: '', label: 'همه وضعیت‌ها' },
  { value: 'true', label: 'فعال' },
  { value: 'false', label: 'غیرفعال' },
]

const { data, pending, error, refresh } = await useAsyncData(
  'admin-users',
  () => api<AdminUserListResponse>('/admin/users/', {
    query: {
      q: qDebounced.value || undefined,
      role: roleFilter.value || undefined,
      active: activeFilter.value || undefined,
      limit: PAGE_SIZE,
      offset: offset.value,
    },
  }),
  { watch: [qDebounced, roleFilter, activeFilter, offset] },
)

const rows = computed(() => data.value?.results ?? [])
const total = computed(() => data.value?.count ?? 0)
const summary = computed(() => data.value?.summary ?? null)
const from = computed(() => (total.value === 0 ? 0 : offset.value + 1))
const to = computed(() => Math.min(offset.value + PAGE_SIZE, total.value))

const busy = ref<Record<number, boolean>>({})
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

function initialOf(u: AdminUser) { return (u.username || u.email || '؟').trim().charAt(0).toUpperCase() }
function fullName(u: AdminUser) {
  const name = `${u.first_name || ''} ${u.last_name || ''}`.trim()
  return name || u.username
}
function joinedDate(iso: string) {
  try { return new Intl.DateTimeFormat('fa-IR', { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(iso)) }
  catch { return '—' }
}
function isSelf(u: AdminUser) { return auth.user?.id === u.id }

async function patchUser(u: AdminUser, payload: Record<string, unknown>, okMsg: string) {
  busy.value = { ...busy.value, [u.id]: true }
  try {
    await api(`/admin/users/${u.id}/`, { method: 'PATCH', body: payload })
    notify.success('انجام شد', okMsg)
    await refresh()
  }
  catch (err: unknown) {
    const detail = (err as { data?: { detail?: string } })?.data?.detail
    notify.error('خطا', detail || 'عملیات ناموفق بود')
  }
  finally { busy.value = { ...busy.value, [u.id]: false } }
}

function toggleActive(u: AdminUser) {
  patchUser(u, { is_active: !u.is_active }, u.is_active ? 'حساب غیرفعال شد' : 'حساب فعال شد')
}
function toggleStaff(u: AdminUser) {
  patchUser(u, { is_staff: !u.is_staff }, u.is_staff ? 'دسترسی مدیریت برداشته شد' : 'دسترسی مدیریت داده شد')
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">کاربران</h1>
      <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">{{ fa(summary?.total ?? total) }} کاربر ثبت‌شده</p>
    </div>

    <!-- Summary tiles -->
    <div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <RvStat label="کل کاربران" :value="summary?.total ?? null" :icon="Users" tone="accent" :loading="pending && !summary" />
      <RvStat label="فعال" :value="summary?.active ?? null" :icon="UserCheck" tone="success" :loading="pending && !summary" />
      <RvStat label="مدیران" :value="summary?.staff ?? null" :icon="ShieldCheck" tone="violet" :loading="pending && !summary" />
      <RvStat label="تأییدشده" :value="summary?.verified ?? null" :icon="BadgeCheck" tone="info" :loading="pending && !summary" />
    </div>

    <div class="flex flex-wrap items-center gap-3">
      <div class="relative min-w-[200px] flex-1">
        <Search class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--rv-faint)]" />
        <input v-model="q" type="search" placeholder="جستجوی نام، ایمیل یا شماره…" class="rv-input !pr-9">
      </div>
      <select v-model="roleFilter" class="rv-input !w-auto">
        <option v-for="o in ROLE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <select v-model="activeFilter" class="rv-input !w-auto">
        <option v-for="o in ACTIVE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
    </div>

    <RvPanel :icon="Users" :padded="false">
      <template #actions>
        <span v-if="total" class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
      </template>

      <RvState v-if="error" kind="error" title="خطا در دریافت فهرست" @retry="refresh()" />
      <RvState v-else-if="!pending && rows.length === 0" title="کاربری یافت نشد" message="با فیلترهای دیگری امتحان کنید." />

      <div v-else class="overflow-x-auto">
        <table class="rv-table">
          <thead>
            <tr>
              <th>کاربر</th>
              <th>نقش</th>
              <th>وضعیت</th>
              <th>عضویت</th>
              <th class="text-center">اقدامات</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="pending && rows.length === 0">
              <tr v-for="i in 8" :key="`sk${i}`">
                <td colspan="5"><div class="rv-skeleton h-9 w-full" /></td>
              </tr>
            </template>
            <tr v-for="u in rows" :key="u.id">
              <td>
                <div class="flex items-center gap-3">
                  <span class="grid size-9 shrink-0 place-items-center rounded-full bg-[var(--rv-accent-soft)] text-sm font-black text-[var(--rv-accent)]">{{ initialOf(u) }}</span>
                  <div class="min-w-0">
                    <p class="flex items-center gap-1.5 truncate font-bold text-[var(--rv-text)]">
                      {{ fullName(u) }}
                      <span v-if="isSelf(u)" class="text-[11px] font-black text-[var(--rv-accent)]">(شما)</span>
                    </p>
                    <p class="truncate text-xs text-[var(--rv-faint)]" dir="ltr">{{ u.email }}</p>
                  </div>
                </div>
              </td>
              <td>
                <div class="flex flex-wrap gap-1">
                  <RvBadge v-if="u.is_superuser" tone="danger">ابرکاربر</RvBadge>
                  <RvBadge v-else-if="u.is_staff" tone="violet">مدیر</RvBadge>
                  <RvBadge v-else tone="neutral">کاربر</RvBadge>
                  <RvBadge v-if="u.is_verified" tone="info" dot>تأیید</RvBadge>
                </div>
              </td>
              <td><RvBadge :tone="u.is_active ? 'success' : 'neutral'" dot>{{ u.is_active ? 'فعال' : 'غیرفعال' }}</RvBadge></td>
              <td class="whitespace-nowrap text-[var(--rv-muted)]">{{ joinedDate(u.date_joined) }}</td>
              <td>
                <div class="flex items-center justify-center gap-1">
                  <button
                    type="button" class="rv-icon-btn rv-focus" :disabled="busy[u.id] || isSelf(u)"
                    :title="u.is_staff ? 'برداشتن دسترسی مدیریت' : 'دادن دسترسی مدیریت'"
                    :style="u.is_staff ? { color: 'var(--rv-violet)' } : {}"
                    @click="toggleStaff(u)"
                  >
                    <ShieldCheck class="size-4" />
                  </button>
                  <button
                    type="button" class="rv-icon-btn rv-focus"
                    :class="u.is_active ? 'rv-icon-btn--danger' : ''"
                    :disabled="busy[u.id] || isSelf(u)"
                    :title="u.is_active ? 'غیرفعال‌سازی حساب' : 'فعال‌سازی حساب'"
                    @click="toggleActive(u)"
                  >
                    <component :is="u.is_active ? UserX : UserCheck" class="size-4" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="total > PAGE_SIZE" class="flex items-center justify-between gap-3 border-t border-[var(--rv-border)] px-4 py-3">
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="offset === 0 || pending" @click="offset = Math.max(0, offset - PAGE_SIZE)">
          <ChevronRight class="size-4" /> قبلی
        </button>
        <span class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="to >= total || pending" @click="offset = offset + PAGE_SIZE">
          بعدی <ChevronLeft class="size-4" />
        </button>
      </div>
    </RvPanel>
  </div>
</template>

<script setup lang="ts">
import Plus from '~icons/lucide/plus'
import Refresh from '~icons/lucide/rotate-cw'
import Save from '~icons/lucide/save'
import Search from '~icons/lucide/search'
import Shield from '~icons/lucide/shield'
import Users from '~icons/lucide/users-round'
import type { AdminUser, AdminUserFilters, AppErrorDetails } from '~/types'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'مدیریت کاربران', robots: 'noindex, nofollow' })

const api = useAdminUsers()
const authStore = useAuthStore()
const notifications = useNotifications()

const users = ref<AdminUser[]>([])
const total = ref(0)
const loading = ref(true)
const savingId = ref<number | null>(null)
const creating = ref(false)
const createOpen = ref(false)
const error = ref<AppErrorDetails | null>(null)
const pageSize = 20
const {
  filters,
  page,
  debouncedWatch,
  syncQuery,
  clearFilters,
} = useDebouncedFilters<AdminUserFilters>({
  q: '',
  role: '',
  active: '',
  limit: pageSize,
  offset: 0,
}, {
  urlKeys: ['q', 'role', 'active'],
})
const filterDefaults: Partial<AdminUserFilters> = { q: '', role: '', active: '' }

const createForm = reactive({
  email: '',
  username: '',
  password: '',
  first_name: '',
  last_name: '',
  is_staff: false,
  is_active: true,
  is_verified: false,
})

const drafts = reactive<Record<number, Partial<AdminUser> & { password?: string }>>({})
const meId = computed(() => authStore.user?.id)

function draftFor(user: AdminUser) {
  if (!drafts[user.id]) {
    drafts[user.id] = {
      is_active: user.is_active,
      is_staff: user.is_staff,
      is_superuser: user.is_superuser,
      is_verified: user.is_verified,
      password: '',
    }
  }
  return drafts[user.id]
}

async function loadUsers(silent = false) {
  if (!silent) loading.value = true
  filters.offset = (page.value - 1) * pageSize
  filters.limit = pageSize
  try {
    const response = await api.list(filters)
    users.value = response.results
    total.value = response.count
    for (const user of response.results) {
      drafts[user.id] = {
        is_active: user.is_active,
        is_staff: user.is_staff,
        is_superuser: user.is_superuser,
        is_verified: user.is_verified,
        password: '',
      }
    }
    error.value = null
  }
  catch (cause) {
    if (!silent) error.value = getAppError(cause, 'فهرست کاربران دریافت نشد.')
  }
  finally {
    if (!silent) loading.value = false
  }
}

async function saveUser(user: AdminUser) {
  const draft = draftFor(user)
  savingId.value = user.id
  try {
    const payload: Record<string, unknown> = {
      is_active: Boolean(draft.is_active),
      is_staff: Boolean(draft.is_staff),
      is_verified: Boolean(draft.is_verified),
    }
    if (authStore.user?.is_superuser) {
      payload.is_superuser = Boolean(draft.is_superuser)
    }
    if (draft.password?.trim()) {
      payload.password = draft.password.trim()
    }
    const updated = await api.update(user.id, payload)
    const index = users.value.findIndex(item => item.id === user.id)
    if (index >= 0) users.value[index] = updated
    drafts[user.id] = {
      is_active: updated.is_active,
      is_staff: updated.is_staff,
      is_superuser: updated.is_superuser,
      is_verified: updated.is_verified,
      password: '',
    }
    notifications.success('ذخیره شد', `کاربر ${updated.username} به‌روز شد.`)
  }
  catch (cause) {
    notifications.notifyError(cause, 'ذخیره نشد')
  }
  finally {
    savingId.value = null
  }
}

async function createUser() {
  creating.value = true
  try {
    await api.create({ ...createForm })
    notifications.success('کاربر ساخته شد', createForm.email)
    createOpen.value = false
    Object.assign(createForm, {
      email: '', username: '', password: '', first_name: '', last_name: '',
      is_staff: false, is_active: true, is_verified: false,
    })
    page.value = 1
    await loadUsers()
  }
  catch (cause) {
    notifications.notifyError(cause, 'ساخت کاربر ناموفق بود')
  }
  finally {
    creating.value = false
  }
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  }
  catch {
    return value
  }
}

debouncedWatch(() => {
  syncQuery()
  void loadUsers()
}, [() => filters.role, () => filters.active])

watch(page, () => {
  syncQuery()
  void loadUsers()
})

onMounted(() => { void loadUsers() })
</script>

<template>
  <div class="space-y-5 px-4 py-5 sm:px-6 lg:px-8">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p class="text-xs font-black tracking-[.16em] text-[var(--admin-muted)]">ADMIN · USERS</p>
        <h1 class="mt-1 text-2xl font-black text-[var(--admin-text)]">مدیریت کاربران</h1>
        <p class="mt-1 text-sm text-[var(--admin-muted)]">فعال/غیرفعال، دسترسی مدیریت، و ساخت کاربر جدید.</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <AdminButton :loading="loading" variant="ghost" @click="loadUsers()">
          <Refresh class="size-4" /> بروزرسانی
        </AdminButton>
        <AdminButton @click="createOpen = true">
          <Plus class="size-4" /> کاربر جدید
        </AdminButton>
      </div>
    </div>

    <AdminCard class="p-4 sm:p-5">
      <div class="grid gap-3 md:grid-cols-[1fr_10rem_10rem_auto]">
        <AdminField label="جستجو">
          <div class="relative">
            <Search class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--admin-muted)]" />
            <input v-model="filters.q" class="admin-input w-full pr-10" placeholder="ایمیل، نام کاربری، تلفن…" >
          </div>
        </AdminField>
        <AdminField label="نقش">
          <select v-model="filters.role" class="admin-input w-full">
            <option value="">همه</option>
            <option value="staff">مدیر</option>
            <option value="user">کاربر عادی</option>
          </select>
        </AdminField>
        <AdminField label="وضعیت">
          <select v-model="filters.active" class="admin-input w-full">
            <option value="">همه</option>
            <option value="true">فعال</option>
            <option value="false">غیرفعال</option>
          </select>
        </AdminField>
        <button
          v-if="filters.q || filters.role || filters.active"
          type="button"
          class="admin-focus inline-flex min-h-11 items-center self-end rounded-lg px-2 text-xs font-bold text-[var(--admin-accent)] hover:underline"
          @click="clearFilters(filterDefaults)"
        >
          پاک کردن فیلترها
        </button>
      </div>
    </AdminCard>

    <AdminState v-if="loading" title="در حال بارگذاری کاربران…" message="لطفاً چند لحظه صبر کنید." />
    <AdminState v-else-if="error" kind="error" :title="error.message" message="درخواست فهرست کاربران ناموفق بود." @retry="loadUsers()" />
    <AdminCard v-else class="overflow-hidden">
      <div class="responsive-table">
        <table class="min-w-[860px] text-sm">
          <thead class="bg-[var(--admin-bg)] text-[var(--admin-muted)]">
            <tr>
              <th class="px-3 py-3 text-right font-bold">کاربر</th>
              <th class="px-3 py-3 text-right font-bold">نقش‌ها</th>
              <th class="px-3 py-3 text-right font-bold">وضعیت</th>
              <th class="px-3 py-3 text-right font-bold">آخرین ورود</th>
              <th class="px-3 py-3 text-right font-bold">رمز جدید</th>
              <th class="px-3 py-3 text-right font-bold">عملیات</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id" class="border-t border-[var(--admin-border)] align-top">
              <td class="px-3 py-3">
                <p class="font-black">{{ user.username }}</p>
                <p class="text-xs text-[var(--admin-muted)]" dir="ltr">{{ user.email }}</p>
                <p v-if="user.phone" class="mt-0.5 text-xs text-[var(--admin-muted)]" dir="ltr">{{ user.phone }}</p>
              </td>
              <td class="px-3 py-3">
                <label class="flex min-h-11 items-center gap-2 py-1">
                  <input v-model="draftFor(user).is_staff" type="checkbox" :disabled="user.id === meId">
                  <span>مدیر (staff)</span>
                </label>
                <label v-if="authStore.user?.is_superuser" class="flex min-h-11 items-center gap-2 py-1">
                  <input v-model="draftFor(user).is_superuser" type="checkbox" :disabled="user.id === meId">
                  <span>ابرکاربر</span>
                </label>
                <label class="flex min-h-11 items-center gap-2 py-1">
                  <input v-model="draftFor(user).is_verified" type="checkbox">
                  <span>تأییدشده</span>
                </label>
              </td>
              <td class="px-3 py-3">
                <label class="flex min-h-11 items-center gap-2">
                  <input v-model="draftFor(user).is_active" type="checkbox" :disabled="user.id === meId">
                  <span>{{ draftFor(user).is_active ? 'فعال' : 'غیرفعال' }}</span>
                </label>
                <p v-if="user.locked_until" class="mt-1 text-xs text-amber-700">قفل تا {{ formatDate(user.locked_until) }}</p>
              </td>
              <td class="px-3 py-3 text-xs text-[var(--admin-muted)]">
                <p>{{ formatDate(user.last_login) }}</p>
                <p class="mt-1">عضویت: {{ formatDate(user.date_joined) }}</p>
              </td>
              <td class="px-3 py-3">
                <input
                  v-model="draftFor(user).password"
                  type="password"
                  class="admin-input w-40"
                  placeholder="اختیاری"
                  autocomplete="new-password"
                >
              </td>
              <td class="px-3 py-3">
                <AdminButton size="sm" :loading="savingId === user.id" @click="saveUser(user)">
                  <Save class="size-3.5" /> ذخیره
                </AdminButton>
              </td>
            </tr>
            <tr v-if="!users.length">
              <td colspan="6" class="px-3 py-10 text-center text-[var(--admin-muted)]">
                <Users class="mx-auto size-8 opacity-40" />
                <p class="mt-2">کاربری پیدا نشد.</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <AdminPagination
        :page="page"
        :total="total"
        :page-size="pageSize"
        :loading="loading"
        @update:page="page = $event"
      />
    </AdminCard>

    <AdminModal :open="createOpen" title="کاربر جدید" @close="createOpen = false">
      <div class="grid gap-3 p-5 sm:grid-cols-2 sm:p-6">
        <AdminField label="ایمیل" class="sm:col-span-2">
          <input v-model="createForm.email" type="email" class="admin-input w-full" dir="ltr">
        </AdminField>
        <AdminField label="نام کاربری">
          <input v-model="createForm.username" class="admin-input w-full" dir="ltr">
        </AdminField>
        <AdminField label="رمز عبور">
          <input v-model="createForm.password" type="password" class="admin-input w-full" autocomplete="new-password">
        </AdminField>
        <AdminField label="نام">
          <input v-model="createForm.first_name" class="admin-input w-full">
        </AdminField>
        <AdminField label="نام خانوادگی">
          <input v-model="createForm.last_name" class="admin-input w-full">
        </AdminField>
        <label class="flex items-center gap-2 text-sm"><input v-model="createForm.is_staff" type="checkbox"><Shield class="size-4" /> مدیر</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="createForm.is_active" type="checkbox"> فعال</label>
        <label class="flex items-center gap-2 text-sm sm:col-span-2"><input v-model="createForm.is_verified" type="checkbox"> تأییدشده</label>
      </div>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <AdminButton variant="ghost" @click="createOpen = false">انصراف</AdminButton>
          <AdminButton :loading="creating" :disabled="!createForm.email || !createForm.username || createForm.password.length < 8" @click="createUser">
            ساخت کاربر
          </AdminButton>
        </div>
      </template>
    </AdminModal>
  </div>
</template>

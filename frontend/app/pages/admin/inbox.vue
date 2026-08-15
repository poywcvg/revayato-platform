<script setup lang="ts">
import Inbox from '~icons/lucide/inbox'
import MessageSquare from '~icons/lucide/message-square-text'
import Refresh from '~icons/lucide/rotate-cw'
import Search from '~icons/lucide/search'
import type { AppErrorDetails, SupportStatus, SupportTicket, SupportTicketListItem } from '~/types'

definePageMeta({ layout: 'admin', middleware: ['staff'] })
useSeoMeta({ title: 'صندوق هم‌صدا', robots: 'noindex, nofollow' })

type InboxFilters = { q: string; status: string; category: string; unread: boolean }

const api = useAdminSupport()
const notifications = useNotifications()

const tickets = ref<SupportTicketListItem[]>([])
const active = ref<SupportTicket | null>(null)
const total = ref(0)
const unreadCount = ref(0)
const openCount = ref(0)
const loading = ref(true)
const saving = ref(false)
const error = ref<AppErrorDetails | null>(null)
const pageSize = 20
const replyBody = ref('')
const staffNote = ref('')
const {
  filters,
  page,
  debouncedWatch,
  syncQuery,
  clearFilters,
} = useDebouncedFilters<InboxFilters>({
  q: '',
  status: '',
  category: '',
  unread: false,
}, {
  urlKeys: ['q', 'status', 'category', 'unread'],
})
const filterDefaults = { q: '', status: '', category: '', unread: false }

const statusOptions = [
  { value: '', label: 'همه وضعیت‌ها' },
  { value: 'open', label: 'باز' },
  { value: 'in_progress', label: 'در حال بررسی' },
  { value: 'waiting_user', label: 'منتظر کاربر' },
  { value: 'resolved', label: 'حل‌شده' },
  { value: 'closed', label: 'بسته' },
]

const categoryOptions = [
  { value: '', label: 'همه دسته‌ها' },
  { value: 'content_request', label: 'درخواست عنوان' },
  { value: 'bug', label: 'گزارش مشکل' },
  { value: 'content_fix', label: 'اصلاح محتوا' },
  { value: 'suggestion', label: 'پیشنهاد' },
  { value: 'support', label: 'پشتیبانی' },
  { value: 'cooperation', label: 'همکاری' },
]

async function loadInbox(silent = false) {
  if (!silent) loading.value = true
  try {
    const response = await api.list({
      q: filters.q,
      status: filters.status || undefined,
      category: filters.category || undefined,
      unread: filters.unread,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    tickets.value = response.results
    total.value = response.count
    unreadCount.value = response.unread_count
    openCount.value = response.open_count
    error.value = null
  } catch (cause) {
    if (!silent) error.value = getAppError(cause, 'صندوق پیام دریافت نشد.')
  } finally {
    if (!silent) loading.value = false
  }
}

async function openTicket(code: string) {
  try {
    active.value = await api.detail(code)
    staffNote.value = active.value.staff_note || ''
    replyBody.value = ''
    await loadInbox(true)
  } catch (cause) {
    notifications.notifyError(cause, 'باز کردن گفتگو ناموفق بود.')
  }
}

async function sendReply() {
  if (!active.value || !replyBody.value.trim()) return
  saving.value = true
  try {
    active.value = await api.reply(active.value.tracking_code, replyBody.value.trim())
    replyBody.value = ''
    notifications.success('پاسخ ثبت شد', 'کاربر پاسخ را در صفحه هم‌صدا می‌بیند.')
    await loadInbox(true)
  } catch (cause) {
    notifications.notifyError(cause, 'ارسال پاسخ انجام نشد.')
  } finally {
    saving.value = false
  }
}

async function saveStatus(status: SupportStatus) {
  if (!active.value) return
  saving.value = true
  try {
    active.value = await api.update(active.value.tracking_code, {
      status,
      staff_note: staffNote.value,
    })
    notifications.success('وضعیت به‌روز شد', active.value.status_label)
    await loadInbox(true)
  } catch (cause) {
    notifications.notifyError(cause, 'به‌روزرسانی وضعیت انجام نشد.')
  } finally {
    saving.value = false
  }
}

debouncedWatch(() => {
  syncQuery()
  void loadInbox()
}, [() => filters.status, () => filters.category, () => filters.unread])

watch(page, () => {
  syncQuery()
  void loadInbox()
})
onMounted(() => { void loadInbox() })
</script>

<template>
  <div class="space-y-5 px-4 py-5 sm:px-6 lg:px-8">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p class="text-[11px] font-black text-[var(--admin-muted)]">صندوق هم‌صدا</p>
        <h1 class="mt-1 text-2xl font-black">پیام‌ها و درخواست‌های کاربران</h1>
        <p class="mt-1 text-xs text-[var(--admin-muted)]">
          {{ openCount.toLocaleString('fa-IR') }} باز · {{ unreadCount.toLocaleString('fa-IR') }} خوانده‌نشده
        </p>
      </div>
      <AdminButton variant="secondary" :disabled="loading" @click="loadInbox()">
        <Refresh class="size-4" />بروزرسانی
      </AdminButton>
    </div>

    <AdminCard>
      <div class="grid gap-3 md:grid-cols-4">
        <label class="relative md:col-span-2">
          <Search class="pointer-events-none absolute end-3 top-1/2 size-4 -translate-y-1/2 text-[var(--admin-muted)]" />
          <input v-model="filters.q" class="admin-input w-full pe-10" placeholder="جستجو در موضوع، کد، کاربر…">
        </label>
        <select v-model="filters.status" class="admin-input">
          <option v-for="option in statusOptions" :key="option.value || 'all'" :value="option.value">{{ option.label }}</option>
        </select>
        <select v-model="filters.category" class="admin-input">
          <option v-for="option in categoryOptions" :key="option.value || 'all-cat'" :value="option.value">{{ option.label }}</option>
        </select>
      </div>
      <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
        <label class="inline-flex items-center gap-2 text-xs font-bold text-[var(--admin-muted)]">
          <input v-model="filters.unread" type="checkbox" class="size-4 rounded">
          فقط خوانده‌نشده‌ها
        </label>
        <button
          v-if="filters.q || filters.status || filters.category || filters.unread"
          type="button"
          class="admin-focus inline-flex min-h-11 items-center rounded-lg px-2 text-xs font-bold text-[var(--admin-accent)] hover:underline"
          @click="clearFilters(filterDefaults)"
        >
          پاک کردن فیلترها
        </button>
      </div>
    </AdminCard>

    <AdminState v-if="loading" title="در حال بارگذاری صندوق…" message="لطفاً چند لحظه صبر کنید." />
    <AdminState v-else-if="error" kind="error" :title="error.message" message="صندوق پیام دریافت نشد." @retry="loadInbox()" />

    <div v-else class="grid gap-4 xl:grid-cols-[minmax(18rem,.9fr)_minmax(0,1.3fr)]">
      <AdminCard class="!p-3">
        <ul class="max-h-[70vh] space-y-2 overflow-y-auto">
          <li v-for="ticket in tickets" :key="ticket.tracking_code">
            <button
              type="button"
              class="admin-focus w-full rounded-2xl px-3 py-3 text-start transition"
              :class="active?.tracking_code === ticket.tracking_code ? 'bg-[var(--admin-warm)]/15' : 'hover:bg-[var(--admin-surface-muted)]'"
              @click="openTicket(ticket.tracking_code)"
            >
              <span class="flex items-start justify-between gap-2">
                <span class="min-w-0">
                  <span class="block truncate text-sm font-black">{{ ticket.subject }}</span>
                  <span class="mt-1 block text-[11px] text-[var(--admin-muted)]">{{ ticket.username }} · {{ ticket.category_label }}</span>
                  <span class="font-latin mt-1 block text-[10px] text-[var(--admin-muted)]" dir="ltr">{{ ticket.tracking_code }}</span>
                </span>
                <span v-if="ticket.unread_by_staff" class="mt-1 size-2 shrink-0 rounded-full bg-[var(--admin-warm)]" />
              </span>
              <span class="mt-2 inline-flex rounded-lg bg-[var(--admin-surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--admin-muted)]">{{ ticket.status_label }}</span>
            </button>
          </li>
          <li v-if="!tickets.length" class="px-3 py-8 text-center text-sm text-[var(--admin-muted)]">
            <Inbox class="mx-auto mb-2 size-8 opacity-40" />
            پیامی در این فیلتر نیست.
          </li>
        </ul>
        <AdminPagination
          :page="page"
          :total="total"
          :page-size="pageSize"
          :loading="loading"
          class="!border-0 !px-2 !py-3"
          @update:page="page = $event"
        />
      </AdminCard>

      <AdminCard v-if="active" class="!p-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="text-lg font-black">{{ active.subject }}</h2>
            <p class="mt-1 text-xs text-[var(--admin-muted)]">
              {{ active.username }}
              <span v-if="active.user_email"> · {{ active.user_email }}</span>
              · {{ active.category_label }}
            </p>
            <p class="font-latin mt-1 text-[11px] text-[var(--admin-muted)]" dir="ltr">{{ active.tracking_code }}</p>
          </div>
          <AdminBadge>{{ active.status_label }}</AdminBadge>
        </div>
        <p v-if="active.related_title" class="mt-3 rounded-xl bg-[var(--admin-surface-muted)] px-3 py-2 text-xs">
          عنوان مرتبط: <strong>{{ active.related_title }}</strong>
          <span v-if="active.related_year"> ({{ active.related_year }})</span>
          <a v-if="active.related_url" :href="active.related_url" target="_blank" rel="noopener" class="ms-2 text-[var(--admin-primary)]" dir="ltr">لینک</a>
        </p>

        <div class="mt-4 max-h-[42vh] space-y-3 overflow-y-auto rounded-2xl bg-[var(--admin-bg)] p-3">
          <article
            v-for="message in active.messages"
            :key="message.id"
            class="rounded-xl px-3 py-2.5 text-xs leading-6"
            :class="message.is_staff_reply ? 'bg-[var(--admin-warm)]/18' : 'bg-white ring-1 ring-[var(--admin-border)]'"
          >
            <p class="mb-1 flex items-center gap-1.5 text-[10px] font-black text-[var(--admin-muted)]">
              <MessageSquare class="size-3" />
              {{ message.author_username }}
            </p>
            {{ message.body }}
          </article>
        </div>

        <div class="mt-4 grid gap-3">
          <textarea v-model="replyBody" class="admin-input min-h-28 resize-y" placeholder="پاسخ پشتیبانی برای کاربر…" />
          <div class="flex flex-wrap gap-2">
            <AdminButton :disabled="saving || !replyBody.trim()" @click="sendReply">ارسال پاسخ</AdminButton>
            <AdminButton variant="secondary" :disabled="saving" @click="saveStatus('in_progress')">در حال بررسی</AdminButton>
            <AdminButton variant="secondary" :disabled="saving" @click="saveStatus('resolved')">حل‌شده</AdminButton>
            <AdminButton variant="secondary" :disabled="saving" @click="saveStatus('closed')">بستن</AdminButton>
          </div>
          <label class="grid gap-1.5 text-xs font-bold text-[var(--admin-muted)]">
            یادداشت داخلی ادمین
            <textarea v-model="staffNote" class="admin-input min-h-20 resize-y font-medium" placeholder="فقط برای تیم…" />
          </label>
          <AdminButton variant="secondary" :disabled="saving" @click="saveStatus(active.status)">ذخیره یادداشت</AdminButton>
        </div>
      </AdminCard>

      <AdminCard v-else class="grid min-h-72 place-items-center text-center">
        <div>
          <Inbox class="mx-auto size-10 text-[var(--admin-muted)] opacity-40" />
          <p class="mt-3 text-sm text-[var(--admin-muted)]">یک پیام را از فهرست انتخاب کن.</p>
        </div>
      </AdminCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SupportTicketListItem } from '~/types'
import { SUPPORT_CATEGORY_META, SUPPORT_STATUS_META } from '~/composables/useSupport'
import Headset from '~icons/lucide/headset'
import Search from '~icons/lucide/search'
import Inbox from '~icons/lucide/inbox'
import MailOpen from '~icons/lucide/mail-open'
import ChevronLeft from '~icons/lucide/chevron-left'

definePageMeta({ layout: 'admin', middleware: 'staff' })
useSeoMeta({ title: 'درخواست‌های پشتیبانی — روایتو' })

const { listTickets, refreshOverview, purgeTickets } = useAdminInteraction()
const notify = useNotifications()

const PAGE_SIZE = 20
const q = ref('')
const qDebounced = ref('')
const statusFilter = ref('')
const categoryFilter = ref('')
const unreadOnly = ref(false)
// Resolved/closed conversations are hidden by default so the panel only shows
// work to do; they stay reachable via the status filter until purged.
const hideResolved = ref(true)
const offset = ref(0)

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(q, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { qDebounced.value = val.trim(); offset.value = 0 }, 350)
})
watch([statusFilter, categoryFilter, unreadOnly, hideResolved], () => { offset.value = 0 })

const { data, pending, error, refresh } = await useAsyncData(
  'admin-support',
  () => listTickets({
    status: statusFilter.value || undefined,
    category: categoryFilter.value || undefined,
    unread: unreadOnly.value ? 'true' : undefined,
    hide_resolved: !statusFilter.value && hideResolved.value ? 'true' : undefined,
    q: qDebounced.value || undefined,
    limit: PAGE_SIZE,
    offset: offset.value,
  }),
  { watch: [qDebounced, statusFilter, categoryFilter, unreadOnly, hideResolved, offset] },
)

const rows = computed(() => data.value?.results ?? [])
const total = computed(() => data.value?.count ?? 0)
const unreadCount = computed(() => data.value?.unread_count ?? 0)
const openCount = computed(() => data.value?.open_count ?? 0)
const from = computed(() => (total.value === 0 ? 0 : offset.value + 1))
const to = computed(() => Math.min(offset.value + PAGE_SIZE, total.value))
const fa = (n: number | null | undefined) => (n ?? 0).toLocaleString('fa-IR')

const STATUS_OPTIONS = [
  { value: '', label: 'همهٔ وضعیت‌ها' },
  ...Object.entries(SUPPORT_STATUS_META).map(([value, meta]) => ({ value, label: meta.label })),
]
const CATEGORY_OPTIONS = [
  { value: '', label: 'همهٔ دسته‌ها' },
  ...Object.entries(SUPPORT_CATEGORY_META).map(([value, meta]) => ({ value, label: meta.label })),
]

function categoryMeta(t: SupportTicketListItem) {
  return SUPPORT_CATEGORY_META[t.category] ?? { label: t.category_label, icon: 'comments' as const }
}
function statusTone(t: SupportTicketListItem): 'accent' | 'success' | 'warning' | 'danger' | 'info' | 'violet' | 'neutral' {
  const map: Record<string, 'info' | 'warning' | 'violet' | 'success' | 'neutral'> = {
    open: 'info', in_progress: 'warning', waiting_user: 'violet', resolved: 'success', closed: 'neutral',
  }
  return map[t.status] ?? 'neutral'
}
function dateOf(iso: string) {
  try { return new Intl.DateTimeFormat('fa-IR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso)) }
  catch { return '—' }
}

// Permanent removal of finished conversations. Capped server-side (200 per
// click) so one press cannot wipe history unseen; the list refreshes after.
const purging = ref(false)
async function purgeResolved() {
  if (purging.value) return
  const scope = categoryFilter.value ? ' همین دسته' : ''
  if (!window.confirm(`گفتگوهای حل‌شده و بسته${scope} برای همیشه از پنل حذف شوند؟ این کار قابل بازگشت نیست.`)) return
  purging.value = true
  try {
    const res = await purgeTickets(categoryFilter.value ? { category: categoryFilter.value } : {})
    notify.success('حذف شد', `${fa(res.deleted)} گفتگوی حل‌شده از پنل حذف شد.`)
    await refresh()
    await refreshOverview()
  } catch (err) {
    notify.notifyError(err, 'حذف گروهی ممکن نشد.')
  } finally {
    purging.value = false
  }
}

onMounted(() => { void refreshOverview() })
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-xl font-black text-[var(--rv-text)] sm:text-2xl">درخواست‌های پشتیبانی</h1>
      <p class="mt-1 text-xs font-semibold text-[var(--rv-muted)]">پاسخ به درخواست‌ها، گزارش‌ها و پیام‌های کاربران</p>
    </div>

    <div class="grid grid-cols-2 gap-4 sm:grid-cols-3">
      <RvStat label="کل درخواست‌ها" :value="total" :icon="Headset" tone="accent" :loading="pending && !data" />
      <RvStat label="باز" :value="openCount" :icon="Inbox" tone="info" :loading="pending && !data" />
      <RvStat label="خوانده‌نشده" :value="unreadCount" :icon="MailOpen" tone="warning" :loading="pending && !data" />
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-center gap-3">
      <div class="relative min-w-[180px] flex-1">
        <Search class="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--rv-faint)]" />
        <input v-model="q" type="search" placeholder="جستجو در موضوع، کد پیگیری یا نام کاربر…" class="rv-input !pr-9">
      </div>
      <select v-model="statusFilter" class="rv-input !w-auto">
        <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <select v-model="categoryFilter" class="rv-input !w-auto">
        <option v-for="o in CATEGORY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <button
        type="button"
        class="rv-btn rv-focus !min-h-[2.6rem]"
        :class="unreadOnly ? 'rv-btn--primary' : 'rv-btn--ghost'"
        @click="unreadOnly = !unreadOnly"
      >
        <MailOpen class="size-4" /> فقط خوانده‌نشده
      </button>
      <button
        v-if="!statusFilter"
        type="button"
        class="rv-btn rv-focus !min-h-[2.6rem]"
        :class="hideResolved ? 'rv-btn--primary' : 'rv-btn--ghost'"
        title="گفتگوهای حل‌شده و بسته از فهرست مخفی می‌شوند"
        @click="hideResolved = !hideResolved"
      >
        مخفی کردن حل‌شده‌ها
      </button>
      <button
        type="button"
        class="rv-btn rv-focus !min-h-[2.6rem]"
        :style="{ color: 'var(--rv-danger)' }"
        :disabled="purging"
        title="حذف دائمی گفتگوهای حل‌شده و بسته (تا ۲۰۰ مورد در هر کلیک)"
        @click="purgeResolved"
      >
        {{ purging ? 'در حال حذف…' : 'حذف حل‌شده‌ها' }}
      </button>
    </div>

    <RvPanel :icon="Headset" :padded="false">
      <template #actions>
        <span v-if="total" class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
      </template>

      <RvState v-if="error" kind="error" title="خطا در دریافت درخواست‌ها" @retry="refresh()" />
      <RvState v-else-if="!pending && rows.length === 0" title="درخواستی یافت نشد" message="با فیلترهای دیگری امتحان کنید." />

      <div v-else-if="pending && rows.length === 0" class="space-y-3 p-4">
        <div v-for="n in 5" :key="n" class="h-16 animate-pulse rounded-[var(--rv-radius)] bg-[var(--rv-surface-2)]" />
      </div>

      <ul v-else class="divide-y divide-[var(--rv-border)]">
        <li v-for="t in rows" :key="t.tracking_code">
          <NuxtLink
            :to="`/admin/support/${t.tracking_code}`"
            class="rv-focus flex items-center gap-3.5 px-4 py-3.5 transition hover:bg-[var(--rv-surface-2)]"
          >
            <span class="grid size-10 shrink-0 place-items-center rounded-[var(--rv-radius-sm)] bg-[var(--rv-accent-soft)] text-[var(--rv-accent)]">
              <CinematicIcon :name="categoryMeta(t).icon" class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span v-if="t.unread_by_staff" class="size-2 shrink-0 rounded-full bg-[var(--rv-warning)]" aria-label="خوانده‌نشده" />
                <h3 class="truncate text-sm font-black text-[var(--rv-text)]">{{ t.subject }}</h3>
              </div>
              <p class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs font-semibold text-[var(--rv-muted)]">
                <span class="text-[var(--rv-text)]">{{ t.username }}</span>
                <span aria-hidden="true">·</span>
                <span>{{ categoryMeta(t).label }}</span>
                <span aria-hidden="true">·</span>
                <span class="font-latin" dir="ltr">#{{ t.tracking_code }}</span>
                <span aria-hidden="true">·</span>
                <span>{{ dateOf(t.last_message_at) }}</span>
                <span v-if="t.message_count > 1" aria-hidden="true">·</span>
                <span v-if="t.message_count > 1">{{ fa(t.message_count) }} پیام</span>
              </p>
            </div>
            <RvBadge :tone="statusTone(t)">{{ t.status_label }}</RvBadge>
            <ChevronLeft class="size-4 shrink-0 text-[var(--rv-faint)]" />
          </NuxtLink>
        </li>
      </ul>

      <div v-if="total > PAGE_SIZE" class="flex items-center justify-between gap-3 border-t border-[var(--rv-border)] px-4 py-3">
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="offset === 0" @click="offset = Math.max(0, offset - PAGE_SIZE)">
          قبلی
        </button>
        <span class="text-xs font-bold text-[var(--rv-muted)]">{{ fa(from) }}–{{ fa(to) }} از {{ fa(total) }}</span>
        <button type="button" class="rv-btn rv-btn--subtle rv-focus !min-h-9" :disabled="to >= total" @click="offset = offset + PAGE_SIZE">
          بعدی
        </button>
      </div>
    </RvPanel>
  </div>
</template>

<script setup lang="ts">
import { SUPPORT_CATEGORY_META, SUPPORT_STATUS_META } from '~/composables/useSupport'
import ArrowRight from '~icons/lucide/arrow-right'
import ShieldCheck from '~icons/lucide/shield-check'
import UserIcon from '~icons/lucide/user'
import Send from '~icons/lucide/send-horizontal'
import Save from '~icons/lucide/save'
import Mail from '~icons/lucide/mail'
import Film from '~icons/lucide/film'

definePageMeta({ layout: 'admin', middleware: 'staff' })

const route = useRoute()
const code = computed(() => String(route.params.code || ''))

const { ticketDetail, replyTicket, patchTicket, deleteTicket, refreshOverview } = useAdminInteraction()
const notify = useNotifications()
const router = useRouter()

const { data: ticket, pending, error, refresh } = await useAsyncData(
  () => `admin-support-${code.value}`,
  () => ticketDetail(code.value),
  { watch: [code] },
)

useSeoMeta({ title: () => (ticket.value ? `${ticket.value.subject} — پشتیبانی` : 'درخواست — روایتو') })

const categoryMeta = computed(() => {
  const t = ticket.value
  if (!t) return { label: '', icon: 'comments' as const }
  return SUPPORT_CATEGORY_META[t.category] ?? { label: t.category_label, icon: 'comments' as const }
})

const thread = computed(() => {
  const t = ticket.value
  if (!t) return []
  const opener = { id: -1, body: t.body, is_staff_reply: false, author_username: t.username, created_at: t.created_at }
  return [opener, ...(t.messages ?? [])]
})

function dateOf(iso: string) {
  try { return new Intl.DateTimeFormat('fa-IR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso)) }
  catch { return '—' }
}

const STATUS_ENTRIES = Object.entries(SUPPORT_STATUS_META) as Array<[string, { label: string }]>

// Reply
const draft = ref('')
const sending = ref(false)
async function sendReply() {
  const body = draft.value.trim()
  if (!body || sending.value) return
  sending.value = true
  try {
    ticket.value = await replyTicket(code.value, body)
    draft.value = ''
    notify.success('ارسال شد', 'پاسخ برای کاربر ثبت شد.')
    await refreshOverview()
  } catch (err) {
    notify.notifyError(err, 'ارسال پاسخ ممکن نشد.')
  } finally {
    sending.value = false
  }
}

// Status
const statusBusy = ref(false)
async function changeStatus(status: string) {
  if (statusBusy.value || status === ticket.value?.status) return
  statusBusy.value = true
  try {
    ticket.value = await patchTicket(code.value, { status })
    notify.success('انجام شد', 'وضعیت درخواست به‌روزرسانی شد.')
    await refreshOverview()
  } catch (err) {
    notify.notifyError(err, 'تغییر وضعیت ممکن نشد.')
  } finally {
    statusBusy.value = false
  }
}

// Internal staff note
const note = ref('')
const noteBusy = ref(false)
const noteDirty = computed(() => note.value !== (ticket.value?.staff_note ?? ''))
watch(ticket, (t) => { if (t) note.value = t.staff_note ?? '' }, { immediate: true })
async function saveNote() {
  if (noteBusy.value || !noteDirty.value) return
  noteBusy.value = true
  try {
    ticket.value = await patchTicket(code.value, { staff_note: note.value })
    notify.success('ذخیره شد', 'یادداشت داخلی ذخیره شد.')
  } catch (err) {
    notify.notifyError(err, 'ذخیرهٔ یادداشت ممکن نشد.')
  } finally {
    noteBusy.value = false
  }
}

// Permanent removal of this conversation from the panel.
const deleting = ref(false)
async function removeTicket() {
  if (deleting.value || !ticket.value) return
  if (!window.confirm(`گفتگوی #${ticket.value.tracking_code} برای همیشه حذف شود؟ این کار قابل بازگشت نیست.`)) return
  deleting.value = true
  try {
    await deleteTicket(code.value)
    notify.success('حذف شد', 'گفتگو از پنل حذف شد.')
    await refreshOverview()
    await router.replace('/admin/support')
  } catch (err) {
    notify.notifyError(err, 'حذف گفتگو ممکن نشد.')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="space-y-5">
    <NuxtLink to="/admin/support" class="rv-focus inline-flex items-center gap-1.5 text-xs font-bold text-[var(--rv-muted)] transition hover:text-[var(--rv-text)]">
      <ArrowRight class="size-4" /> همهٔ درخواست‌ها
    </NuxtLink>

    <div v-if="pending" class="space-y-4">
      <div class="h-24 animate-pulse rounded-[var(--rv-radius)] bg-[var(--rv-surface-2)]" />
      <div class="h-64 animate-pulse rounded-[var(--rv-radius)] bg-[var(--rv-surface-2)]" />
    </div>

    <RvState v-else-if="error || !ticket" kind="error" title="این درخواست پیدا نشد" @retry="refresh()" />

    <div v-else class="grid gap-5 lg:grid-cols-[1fr_320px]">
      <!-- Conversation column -->
      <div class="min-w-0 space-y-5">
        <!-- Header -->
        <div class="rv-card rv-card--glass p-4">
          <div class="flex items-start gap-3">
            <span class="grid size-11 shrink-0 place-items-center rounded-[var(--rv-radius-sm)] bg-[var(--rv-accent-soft)] text-[var(--rv-accent)]">
              <CinematicIcon :name="categoryMeta.icon" class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <h1 class="text-base font-black leading-tight text-[var(--rv-text)]">{{ ticket.subject }}</h1>
              <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-semibold text-[var(--rv-muted)]">
                <span class="text-[var(--rv-text)]">{{ ticket.username }}</span>
                <span aria-hidden="true">·</span>
                <span>{{ categoryMeta.label }}</span>
                <span aria-hidden="true">·</span>
                <span class="font-latin" dir="ltr">#{{ ticket.tracking_code }}</span>
                <span aria-hidden="true">·</span>
                <span>{{ dateOf(ticket.created_at) }}</span>
              </p>
              <NuxtLink
                v-if="ticket.related_title"
                :to="ticket.related_url || undefined"
                target="_blank"
                class="rv-focus mt-2 inline-flex items-center gap-1.5 rounded-full bg-[var(--rv-surface-2)] px-3 py-1 text-xs font-bold text-[var(--rv-muted)] transition hover:text-[var(--rv-text)]"
              >
                <Film class="size-3.5" />
                {{ ticket.related_title }}<template v-if="ticket.related_year"> ({{ ticket.related_year }})</template>
              </NuxtLink>
            </div>
          </div>
        </div>

        <!-- Thread -->
        <ol class="flex flex-col gap-3">
          <li v-for="msg in thread" :key="msg.id" class="msg" :class="msg.is_staff_reply ? 'msg--staff' : 'msg--user'">
            <div class="msg__bubble">
              <div class="msg__head">
                <span class="msg__author">
                  <component :is="msg.is_staff_reply ? ShieldCheck : UserIcon" class="size-3.5" />
                  {{ msg.is_staff_reply ? 'تیم روایتو' : ticket.username }}
                </span>
                <time class="msg__time">{{ dateOf(msg.created_at) }}</time>
              </div>
              <p class="msg__body">{{ msg.body }}</p>
            </div>
          </li>
        </ol>

        <!-- Reply -->
        <div class="rv-card rv-card--glass p-4">
          <label for="admin-reply" class="mb-2 block text-xs font-black text-[var(--rv-muted)]">پاسخ به کاربر</label>
          <textarea
            id="admin-reply"
            v-model="draft"
            rows="4"
            maxlength="5000"
            placeholder="پاسخت را بنویس…"
            class="rv-input !h-auto w-full resize-y !py-2.5 leading-7"
            @keydown.ctrl.enter.prevent="sendReply"
            @keydown.meta.enter.prevent="sendReply"
          />
          <div class="mt-3 flex items-center justify-between gap-3">
            <span class="text-xs text-[var(--rv-faint)]">Ctrl+Enter برای ارسال سریع</span>
            <button type="button" class="rv-btn rv-btn--primary rv-focus" :disabled="sending || !draft.trim()" @click="sendReply">
              <Send class="size-4" /> ارسال پاسخ
            </button>
          </div>
        </div>
      </div>

      <!-- Sidebar column -->
      <aside class="space-y-5">
        <!-- Status -->
        <div class="rv-card rv-card--glass p-4">
          <p class="mb-2.5 text-xs font-black text-[var(--rv-muted)]">وضعیت درخواست</p>
          <div class="flex flex-col gap-1.5">
            <button
              v-for="[value, meta] in STATUS_ENTRIES"
              :key="value"
              type="button"
              class="rv-focus flex items-center justify-between rounded-[var(--rv-radius-sm)] px-3 py-2 text-xs font-black transition"
              :class="ticket.status === value
                ? 'bg-[var(--rv-accent-soft)] text-[var(--rv-accent)] ring-1 ring-[var(--rv-accent-line)]'
                : 'text-[var(--rv-muted)] hover:bg-[var(--rv-surface-2)] hover:text-[var(--rv-text)]'"
              :disabled="statusBusy"
              @click="changeStatus(value)"
            >
              {{ meta.label }}
              <span v-if="ticket.status === value" class="size-2 rounded-full bg-[var(--rv-accent)]" />
            </button>
          </div>
        </div>

        <!-- Contact -->
        <div class="rv-card rv-card--glass p-4">
          <p class="mb-2 text-xs font-black text-[var(--rv-muted)]">کاربر</p>
          <div class="flex items-center gap-2 text-xs font-bold text-[var(--rv-text)]">
            <Mail class="size-4 text-[var(--rv-faint)]" />
            <a :href="`mailto:${ticket.user_email}`" class="rv-focus truncate hover:text-[var(--rv-accent)]" dir="ltr">{{ ticket.user_email }}</a>
          </div>
        </div>

        <!-- Internal note -->
        <div class="rv-card rv-card--glass p-4">
          <p class="mb-2 text-xs font-black text-[var(--rv-muted)]">یادداشت داخلی</p>
          <p class="mb-2 text-[11px] font-semibold text-[var(--rv-faint)]">فقط برای تیم؛ کاربر آن را نمی‌بیند.</p>
          <textarea
            v-model="note"
            rows="4"
            maxlength="5000"
            placeholder="یادداشتی برای تیم…"
            class="rv-input !h-auto w-full resize-y !py-2.5 text-xs leading-6"
          />
          <button type="button" class="rv-btn rv-btn--ghost rv-focus mt-2 w-full !min-h-9" :disabled="noteBusy || !noteDirty" @click="saveNote">
            <Save class="size-4" /> ذخیرهٔ یادداشت
          </button>
        </div>

        <!-- Danger zone -->
        <div class="rv-card rv-card--glass p-4">
          <p class="mb-2 text-xs font-black text-[var(--rv-muted)]">حذف از پنل</p>
          <p class="mb-3 text-[11px] font-semibold leading-5 text-[var(--rv-faint)]">گفتگو و همهٔ پیام‌هایش برای همیشه حذف می‌شوند.</p>
          <button
            type="button"
            class="rv-btn rv-focus w-full !min-h-9"
            :style="{ color: 'var(--rv-danger)' }"
            :disabled="deleting"
            @click="removeTicket"
          >
            {{ deleting ? 'در حال حذف…' : 'حذف این گفتگو' }}
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.msg { display: flex; }
.msg--user { justify-content: flex-start; }
.msg--staff { justify-content: flex-end; }

.msg__bubble {
  max-width: min(90%, 34rem);
  padding: 0.7rem 0.9rem;
  border-radius: var(--rv-radius);
  border: 1px solid var(--rv-border);
  background: var(--rv-surface);
}
.msg--staff .msg__bubble {
  background: var(--rv-accent-soft);
  border-color: var(--rv-accent-line);
  border-bottom-left-radius: 0.35rem;
}
.msg--user .msg__bubble { border-bottom-right-radius: 0.35rem; }

.msg__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.3rem;
}
.msg__author {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 12px;
  font-weight: 900;
  color: var(--rv-muted);
}
.msg--staff .msg__author { color: var(--rv-accent); }
.msg__time { font-size: 12px; color: var(--rv-faint); }
.msg__body {
  font-size: 13px;
  line-height: 1.85;
  color: var(--rv-text);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

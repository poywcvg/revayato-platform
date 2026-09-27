<script setup lang="ts">
import { SUPPORT_CATEGORY_META } from '~/composables/useSupport'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const code = computed(() => String(route.params.code || ''))

const { detail, reply } = useSupport()
const { notifyError, success } = useNotifications()

const { data: ticket, pending, error, refresh } = await useAsyncData(
  () => `request-${code.value}`,
  () => detail(code.value),
  { watch: [code] },
)

useSeoMeta({
  title: () => (ticket.value ? `${ticket.value.subject} — درخواست‌ها` : 'درخواست — روایتو'),
  description: 'گفت‌وگوی پشتیبانی شما با تیم روایتو.',
})

const categoryMeta = computed(() => {
  const t = ticket.value
  if (!t) return { label: '', icon: 'comments' as const }
  return SUPPORT_CATEGORY_META[t.category] ?? { label: t.category_label, icon: 'comments' as const }
})

const isClosed = computed(() => ['resolved', 'closed'].includes(ticket.value?.status ?? ''))

/** The opening body + every follow-up message, oldest → newest, as one thread. */
const thread = computed(() => {
  const t = ticket.value
  if (!t) return []
  const opener = {
    id: -1,
    body: t.body,
    is_staff_reply: false,
    author_username: t.username,
    created_at: t.created_at,
  }
  return [opener, ...(t.messages ?? [])]
})

const dateFmt = new Intl.DateTimeFormat('fa-IR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })
function when(iso: string) {
  try { return dateFmt.format(new Date(iso)) } catch { return '' }
}

const draft = ref('')
const sending = ref(false)
const threadEnd = ref<HTMLElement | null>(null)

async function scrollToEnd() {
  await nextTick()
  threadEnd.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}

async function submit() {
  const body = draft.value.trim()
  if (!body || sending.value || isClosed.value) return
  sending.value = true
  try {
    const updated = await reply(code.value, body)
    ticket.value = updated
    draft.value = ''
    success('پیام ارسال شد', 'پاسخ شما برای تیم روایتو ثبت شد.')
    await scrollToEnd()
  } catch (err) {
    notifyError(err, 'ارسال پیام ممکن نشد.')
  } finally {
    sending.value = false
  }
}

onMounted(() => { void scrollToEnd() })
</script>

<template>
  <div class="page-section pb-12">
    <NuxtLink to="/requests" class="mb-4 inline-flex items-center gap-1.5 text-xs font-bold text-muted transition-colors hover:text-ink">
      <CinematicIcon name="arrow-right" class="size-4" />
      <span>همهٔ درخواست‌ها</span>
    </NuxtLink>

    <div v-if="pending" class="space-y-4">
      <div class="h-28 animate-pulse rounded-3xl bg-elevated ring-1 ring-line" />
      <div class="h-40 animate-pulse rounded-3xl bg-elevated ring-1 ring-line" />
    </div>

    <EmptyState
      v-else-if="error || !ticket"
      icon="info"
      title="این درخواست پیدا نشد"
      description="ممکن است کد پیگیری اشتباه باشد یا این درخواست به حساب شما تعلق نداشته باشد."
      action-label="بازگشت به درخواست‌ها"
      action-href="/requests"
    />

    <template v-else>
      <!-- Header card -->
      <header class="req-head">
        <span class="req-head__icon">
          <CinematicIcon :name="categoryMeta.icon" class="size-5" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="text-lg font-black leading-tight text-ink">{{ ticket.subject }}</h1>
            <SupportStatusPill :status="ticket.status" size="sm" />
          </div>
          <p class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
            <span class="font-bold text-secondary">{{ categoryMeta.label }}</span>
            <span aria-hidden="true">·</span>
            <span class="font-latin" dir="ltr">#{{ ticket.tracking_code }}</span>
            <span aria-hidden="true">·</span>
            <span>ثبت {{ when(ticket.created_at) }}</span>
          </p>
          <NuxtLink
            v-if="ticket.related_title"
            :to="ticket.related_url || undefined"
            class="mt-2 inline-flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1 text-xs font-bold text-secondary ring-1 ring-line transition-colors hover:text-ink"
          >
            <CinematicIcon name="film" class="size-3.5" />
            <span>{{ ticket.related_title }}<template v-if="ticket.related_year"> ({{ ticket.related_year }})</template></span>
          </NuxtLink>
        </div>
      </header>

      <!-- Conversation thread -->
      <ol class="mt-5 flex flex-col gap-3">
        <li
          v-for="msg in thread"
          :key="msg.id"
          class="msg"
          :class="msg.is_staff_reply ? 'msg--staff' : 'msg--user'"
        >
          <div class="msg__bubble">
            <div class="msg__head">
              <span class="msg__author">
                <CinematicIcon :name="msg.is_staff_reply ? 'shield-check' : 'user'" class="size-3.5" />
                {{ msg.is_staff_reply ? 'تیم روایتو' : 'شما' }}
              </span>
              <time class="msg__time">{{ when(msg.created_at) }}</time>
            </div>
            <p class="msg__body">{{ msg.body }}</p>
          </div>
        </li>
      </ol>
      <div ref="threadEnd" />

      <!-- Reply composer -->
      <div v-if="!isClosed" class="mt-5 rounded-3xl bg-elevated p-4 ring-1 ring-line">
        <label for="reply" class="mb-2 block text-xs font-black text-secondary">پاسخ شما</label>
        <textarea
          id="reply"
          v-model="draft"
          rows="3"
          maxlength="4000"
          placeholder="پیامت را بنویس…"
          class="w-full resize-y rounded-2xl border border-line bg-transparent px-3.5 py-2.5 text-sm leading-7 text-ink outline-none transition-colors placeholder:text-muted focus:border-primary-400/60"
          @keydown.ctrl.enter.prevent="submit"
          @keydown.meta.enter.prevent="submit"
        />
        <div class="mt-3 flex items-center justify-between gap-3">
          <span class="text-xs text-muted">برای ارسال سریع Ctrl+Enter بزن</span>
          <UiButtonA variant="primary" :loading="sending" :disabled="!draft.trim()" @click="submit">
            <CinematicIcon name="arrow-left" class="size-4" />
            <span>ارسال پاسخ</span>
          </UiButtonA>
        </div>
      </div>

      <div v-else class="mt-5 flex items-center gap-2.5 rounded-3xl bg-white/4 p-4 text-xs text-muted ring-1 ring-line">
        <CinematicIcon name="check-circle" class="size-4 text-emerald-400" />
        <span>این گفت‌وگو {{ ticket.status === 'resolved' ? 'حل‌شده' : 'بسته' }} است. برای موضوع تازه یک درخواست جدید ثبت کن.</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.req-head {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  padding: 1.1rem 1.15rem;
  border-radius: 1.5rem;
  background: var(--theme-bg-surface, var(--surface-1));
  border: 1px solid color-mix(in srgb, var(--theme-border, #ffffff22) 80%, transparent);
}

.req-head__icon {
  display: grid;
  width: 2.75rem;
  height: 2.75rem;
  flex: none;
  place-items: center;
  border-radius: 0.95rem;
  background: color-mix(in srgb, var(--theme-accent-primary, #7c5cff) 14%, transparent);
  color: var(--theme-accent-primary, #7c5cff);
}

.msg {
  display: flex;
}

.msg--user { justify-content: flex-start; }
.msg--staff { justify-content: flex-end; }

.msg__bubble {
  max-width: min(88%, 40rem);
  padding: 0.75rem 0.95rem;
  border-radius: 1.25rem;
  border: 1px solid color-mix(in srgb, var(--theme-border, #ffffff22) 80%, transparent);
  background: var(--theme-bg-surface, var(--surface-1));
}

.msg--user .msg__bubble {
  border-bottom-right-radius: 0.4rem;
}

.msg--staff .msg__bubble {
  border-bottom-left-radius: 0.4rem;
  background: color-mix(in srgb, var(--theme-accent-primary, #7c5cff) 9%, var(--theme-bg-surface, var(--surface-1)));
  border-color: color-mix(in srgb, var(--theme-accent-primary, #7c5cff) 32%, transparent);
}

.msg__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.35rem;
}

.msg__author {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 12px;
  font-weight: 900;
  color: var(--theme-text-secondary, var(--text-secondary));
}

.msg--staff .msg__author {
  color: var(--theme-accent-primary, #7c5cff);
}

.msg__time {
  font-size: 12px;
  color: var(--theme-text-muted, var(--text-muted));
}

.msg__body {
  font-size: 13px;
  line-height: 1.85;
  color: var(--theme-text-primary, var(--text-primary));
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

<script setup lang="ts">
import type { SupportTicketListItem } from '~/types'
import { SUPPORT_CATEGORY_META } from '~/composables/useSupport'

definePageMeta({ middleware: 'auth' })
useSeoMeta({ title: 'درخواست‌های من — روایتو', description: 'گفت‌وگوهای پشتیبانی و درخواست‌های شما و پاسخ تیم روایتو.' })

const { listMine } = useSupport()
const supportModal = useSupportModal()

const { data, pending, error, refresh } = await useAsyncData('my-requests', () => listMine())

const tickets = computed(() => data.value ?? [])
const openTickets = computed(() => tickets.value.filter(t => !['resolved', 'closed'].includes(t.status)))
const unreadCount = computed(() => tickets.value.filter(t => t.unread_by_user).length)

function categoryMeta(t: SupportTicketListItem) {
  return SUPPORT_CATEGORY_META[t.category] ?? { label: t.category_label, icon: 'comments' as const }
}

const dateFmt = new Intl.DateTimeFormat('fa-IR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })
function when(iso: string) {
  try { return dateFmt.format(new Date(iso)) } catch { return '' }
}

// A request created via the global modal should show up here without a manual reload.
watch(() => supportModal.isOpen.value, (open, was) => { if (was && !open) void refresh() })
</script>

<template>
  <div class="page-section pb-12">
    <PageHero
      title="درخواست‌های من"
      eyebrow="گفت‌وگو با تیم روایتو"
      description="هر درخواست عنوان، گزارش مشکل یا پیام پشتیبانی این‌جا دنبال می‌شود؛ پاسخ تیم روایتو را همین‌جا می‌بینی."
      icon="comments"
    >
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
        <UiButtonA variant="primary" size="lg" @click="supportModal.open()">
          <CinematicIcon name="plus" class="size-5" />
          <span>درخواست جدید</span>
        </UiButtonA>
        <div v-if="tickets.length" class="flex flex-wrap items-center gap-2 text-xs text-muted">
          <span class="rounded-full bg-white/6 px-2.5 py-1 font-bold">{{ tickets.length.toLocaleString('fa-IR') }} درخواست</span>
          <span v-if="openTickets.length" class="rounded-full bg-primary-500/12 px-2.5 py-1 font-bold text-primary-200">{{ openTickets.length.toLocaleString('fa-IR') }} باز</span>
          <span v-if="unreadCount" class="rounded-full bg-violet-500/14 px-2.5 py-1 font-bold text-violet-300">{{ unreadCount.toLocaleString('fa-IR') }} پاسخ خوانده‌نشده</span>
        </div>
      </div>
    </PageHero>

    <div v-if="pending" class="mt-6 space-y-3">
      <div v-for="n in 4" :key="n" class="h-24 animate-pulse rounded-3xl bg-elevated ring-1 ring-line" />
    </div>

    <EmptyState
      v-else-if="error"
      class="mt-6"
      icon="info"
      title="فهرست درخواست‌ها بارگذاری نشد"
      description="اتصال را بررسی کن و دوباره تلاش کن."
    />

    <EmptyState
      v-else-if="!tickets.length"
      class="mt-6"
      icon="comments"
      title="هنوز درخواستی ثبت نکرده‌ای"
      description="یک عنوان می‌خواهی، مشکلی دیده‌ای یا پیشنهادی داری؟ اولین درخواستت را بفرست."
    />

    <ul v-else class="mt-6 flex flex-col gap-3">
      <li v-for="t in tickets" :key="t.tracking_code">
        <NuxtLink :to="`/requests/${t.tracking_code}`" class="req-card group">
          <span class="req-card__icon">
            <CinematicIcon :name="categoryMeta(t).icon" class="size-5" />
          </span>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <h3 class="truncate text-sm font-black text-ink">{{ t.subject }}</h3>
              <span v-if="t.unread_by_user" class="size-2 shrink-0 rounded-full bg-violet-400" aria-label="پاسخ خوانده‌نشده" />
            </div>
            <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
              <span class="font-bold text-secondary">{{ categoryMeta(t).label }}</span>
              <span aria-hidden="true">·</span>
              <span class="font-latin" dir="ltr">#{{ t.tracking_code }}</span>
              <span aria-hidden="true">·</span>
              <span>{{ when(t.last_message_at) }}</span>
              <span v-if="t.message_count > 1" aria-hidden="true">·</span>
              <span v-if="t.message_count > 1">{{ t.message_count.toLocaleString('fa-IR') }} پیام</span>
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <SupportStatusPill :status="t.status" size="sm" />
            <CinematicIcon name="arrow-left" class="size-4 text-muted transition-transform group-hover:-translate-x-0.5" />
          </div>
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.req-card {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 0.9rem 1rem;
  border-radius: 1.25rem;
  background: var(--theme-bg-surface, var(--surface-1));
  border: 1px solid color-mix(in srgb, var(--theme-border, #ffffff22) 80%, transparent);
  transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
}

.req-card:hover,
.req-card:focus-visible {
  border-color: color-mix(in srgb, var(--theme-accent-primary, #7c5cff) 50%, transparent);
  transform: translateY(-1px);
  box-shadow: 0 16px 34px -24px rgb(0 0 0 / 55%);
}

.req-card__icon {
  display: grid;
  width: 2.6rem;
  height: 2.6rem;
  flex: none;
  place-items: center;
  border-radius: 0.9rem;
  background: color-mix(in srgb, var(--theme-accent-primary, #7c5cff) 14%, transparent);
  color: var(--theme-accent-primary, #7c5cff);
}
</style>

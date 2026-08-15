<script setup lang="ts">
import type { SupportCategory, SupportTicket, SupportTicketListItem } from '~/types'

const support = useSupport()
const authStore = useAuthStore()
const route = useRoute()
const notifications = useNotifications()

const categoryOptions = [
  { value: 'content_request', label: 'درخواست فیلم یا سریال' },
  { value: 'bug', label: 'گزارش مشکل سایت یا پخش' },
  { value: 'content_fix', label: 'اصلاح اطلاعات یک عنوان' },
  { value: 'suggestion', label: 'پیشنهاد و ایده' },
  { value: 'support', label: 'پشتیبانی و راهنمایی' },
  { value: 'cooperation', label: 'همکاری محتوایی و تجاری' },
] as const

type Category = SupportCategory
const requestedSubject = String(route.query.subject || '')
const categoryMap: Record<string, Category> = {
  support: 'support',
  report: 'bug',
  content: 'content_fix',
  cooperation: 'cooperation',
  suggestion: 'suggestion',
  content_request: 'content_request',
  bug: 'bug',
  content_fix: 'content_fix',
}

const category = ref<Category>(categoryMap[requestedSubject] || 'content_request')
const subject = ref('')
const body = ref('')
const relatedTitle = ref('')
const relatedYear = ref<string>('')
const relatedUrl = ref('')
const submitting = ref(false)
const myTickets = ref<SupportTicketListItem[]>([])
const activeTicket = ref<SupportTicket | null>(null)
const replyBody = ref('')
const loadingMine = ref(false)
const tab = ref<'compose' | 'inbox'>('compose')

const isContentRequest = computed(() => category.value === 'content_request')

async function loadMine() {
  if (!authStore.isAuthenticated) {
    myTickets.value = []
    return
  }
  loadingMine.value = true
  try {
    myTickets.value = await support.listMine()
  } catch {
    myTickets.value = []
  } finally {
    loadingMine.value = false
  }
}

async function openTicket(code: string) {
  if (!authStore.isAuthenticated) return
  try {
    activeTicket.value = await support.detail(code)
    tab.value = 'inbox'
    replyBody.value = ''
    await loadMine()
  } catch (cause) {
    notifications.notifyError(cause, 'گفتگو باز نشد.')
  }
}

async function submitTicket() {
  if (!authStore.isAuthenticated) {
    await navigateTo({ path: '/auth/login', query: { redirect: '/contact' } })
    return
  }
  if (subject.value.trim().length < 4 || body.value.trim().length < 10) {
    notifications.warning('پیام ناقص است', 'موضوع و متن کامل‌تری بنویس.')
    return
  }
  submitting.value = true
  try {
    const yearRaw = relatedYear.value.trim()
    const ticket = await support.create({
      category: category.value,
      subject: subject.value.trim(),
      body: body.value.trim(),
      related_title: relatedTitle.value.trim(),
      related_year: yearRaw ? Number(yearRaw) : null,
      related_url: relatedUrl.value.trim(),
    })
    notifications.success('پیام ارسال شد', 'به‌زودی پاسخ را همین‌جا می‌بینی.')
    subject.value = ''
    body.value = ''
    relatedTitle.value = ''
    relatedYear.value = ''
    relatedUrl.value = ''
    activeTicket.value = ticket
    tab.value = 'inbox'
    await loadMine()
  } catch (cause) {
    notifications.notifyError(cause, 'ارسال پیام انجام نشد.')
  } finally {
    submitting.value = false
  }
}

async function sendReply() {
  if (!activeTicket.value || !replyBody.value.trim()) return
  submitting.value = true
  try {
    activeTicket.value = await support.reply(activeTicket.value.tracking_code, replyBody.value.trim())
    replyBody.value = ''
    notifications.success('پاسخ ارسال شد')
    await loadMine()
  } catch (cause) {
    notifications.notifyError(cause, 'ارسال پاسخ انجام نشد.')
  } finally {
    submitting.value = false
  }
}

onMounted(() => { void loadMine() })
watch(() => authStore.isAuthenticated, () => { void loadMine() })

useSeoMeta({
  title: 'ارتباط با ما',
  description: 'درخواست فیلم و سریال، گزارش مشکل، پیشنهاد و پشتیبانی روایتو.',
})
</script>

<template>
  <div class="page-section pb-12">
    <PageHero
      title="ارتباط با روایتو"
      eyebrow="پشتیبانی"
      description="فیلم یا سریالی کم داری؟ مشکلی دیدی؟ پیامت را بنویس تا بررسی کنیم."
      icon="comments"
    />

    <div class="mt-5 flex flex-wrap gap-2">
      <button
        type="button"
        class="rounded-xl px-4 py-2.5 text-xs font-black transition"
        :class="tab === 'compose' ? 'bg-primary-500 text-night-950' : 'bg-elevated text-secondary ring-1 ring-line'"
        @click="tab = 'compose'"
      >
        پیام جدید
      </button>
      <button
        type="button"
        class="rounded-xl px-4 py-2.5 text-xs font-black transition"
        :class="tab === 'inbox' ? 'bg-primary-500 text-night-950' : 'bg-elevated text-secondary ring-1 ring-line'"
        @click="tab = 'inbox'"
      >
        پیام‌های من
        <span v-if="myTickets.some(t => t.unread_by_user)" class="ms-1 inline-block size-2 rounded-full bg-brand" />
      </button>
    </div>

    <div class="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(19rem,.85fr)] lg:items-start">
      <section v-if="tab === 'compose'" class="ui-surface p-5 sm:p-7" aria-labelledby="contact-form-title">
        <div class="flex items-start gap-3">
          <span class="grid size-11 shrink-0 place-items-center rounded-2xl bg-primary-500/14 text-brand ring-1 ring-primary-500/20">
            <CinematicIcon name="comment" class="size-5.5" />
          </span>
          <div>
            <h2 id="contact-form-title" class="text-xl font-black text-ink">پیامت را بنویس</h2>
            <p class="mt-1 text-xs leading-6 text-muted">هرچه دقیق‌تر بنویسی، زودتر کمکت می‌کنیم.</p>
          </div>
        </div>

        <form class="mt-6 grid gap-4" @submit.prevent="submitTicket">
          <div>
            <span class="mb-1.5 block text-sm font-bold text-secondary">موضوع</span>
            <UiSelect v-model="category" :options="[...categoryOptions]" label="موضوع" icon="comments" />
          </div>
          <div>
            <label for="contact-subject" class="mb-1.5 block text-sm font-bold text-secondary">عنوان</label>
            <input id="contact-subject" v-model="subject" class="ui-field px-4 text-sm" required minlength="4" :placeholder="isContentRequest ? 'مثلاً: درخواست اضافه شدن Inception' : 'خلاصه موضوع'">
          </div>
          <div v-if="isContentRequest || category === 'content_fix'" class="grid gap-4 sm:grid-cols-2">
            <div>
              <label for="contact-title" class="mb-1.5 block text-sm font-bold text-secondary">نام فیلم / سریال</label>
              <input id="contact-title" v-model="relatedTitle" class="ui-field px-4 text-sm" placeholder="عنوان دقیق">
            </div>
            <div>
              <label for="contact-year" class="mb-1.5 block text-sm font-bold text-secondary">سال</label>
              <input id="contact-year" v-model="relatedYear" class="ui-field px-4 text-sm" inputmode="numeric" placeholder="مثلاً ۲۰۱۰">
            </div>
            <div class="sm:col-span-2">
              <label for="contact-url" class="mb-1.5 block text-sm font-bold text-secondary">لینک IMDb / TMDB (اختیاری)</label>
              <input id="contact-url" v-model="relatedUrl" dir="ltr" class="ui-field px-4 text-left text-sm" placeholder="https://...">
            </div>
          </div>
          <div>
            <label for="contact-body" class="mb-1.5 block text-sm font-bold text-secondary">متن پیام</label>
            <textarea id="contact-body" v-model="body" class="ui-field min-h-40 resize-y px-4 py-3 text-sm leading-7" required minlength="10" placeholder="جزئیات را بنویس. برای درخواست عنوان، ژانر یا نسخه دوبله/زیرنویس موردنظرت را هم بگو." />
          </div>
          <button type="submit" class="ui-primary-button" :disabled="submitting">
            {{ submitting ? 'در حال ارسال…' : 'ارسال' }}
            <CinematicIcon name="arrow-left" class="size-4" />
          </button>
          <p v-if="!authStore.isAuthenticated" class="text-[11px] leading-6 text-muted">
            برای ارسال پیام
            <NuxtLink to="/auth/login?redirect=/contact" class="font-bold text-brand">وارد حساب</NuxtLink>
            شو.
          </p>
        </form>
      </section>

      <section v-else class="ui-surface p-5 sm:p-7" aria-labelledby="contact-inbox-title">
        <h2 id="contact-inbox-title" class="text-xl font-black text-ink">پیام‌های من</h2>
        <p class="mt-1 text-xs text-muted">پیام‌ها و پاسخ‌ها را اینجا ببین.</p>

        <div v-if="!authStore.isAuthenticated" class="mt-6 rounded-2xl bg-elevated p-5 text-sm text-secondary">
          برای دیدن پیام‌ها وارد حساب شو.
          <NuxtLink to="/auth/login?redirect=/contact" class="mt-3 ui-secondary-button w-full">ورود</NuxtLink>
        </div>
        <div v-else-if="loadingMine" class="mt-6 text-sm text-muted">در حال بارگذاری…</div>
        <div v-else class="mt-5 grid gap-4 lg:grid-cols-[minmax(12rem,.9fr)_minmax(0,1.2fr)]">
          <ul class="space-y-2">
            <li v-for="ticket in myTickets" :key="ticket.tracking_code">
              <button
                type="button"
                class="w-full rounded-2xl px-3 py-3 text-start ring-1 transition"
                :class="activeTicket?.tracking_code === ticket.tracking_code
                  ? 'bg-primary-500/12 ring-primary-500/30'
                  : 'bg-elevated ring-line hover:ring-primary-500/25'"
                @click="openTicket(ticket.tracking_code)"
              >
                <span class="flex items-center justify-between gap-2">
                  <strong class="truncate text-sm text-ink">{{ ticket.subject }}</strong>
                  <span v-if="ticket.unread_by_user" class="size-2 shrink-0 rounded-full bg-brand" />
                </span>
                <span class="mt-1 block text-[11px] text-secondary">{{ ticket.status_label }}</span>
              </button>
            </li>
            <li v-if="!myTickets.length" class="rounded-2xl bg-elevated p-4 text-xs text-muted">هنوز پیامی نفرستاده‌ای.</li>
          </ul>

          <div v-if="activeTicket" class="rounded-2xl bg-elevated p-4 ring-1 ring-line">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p class="text-sm font-black text-ink">{{ activeTicket.subject }}</p>
              </div>
              <span class="rounded-lg bg-primary-500/14 px-2 py-1 text-[10px] font-black text-brand">{{ activeTicket.status_label }}</span>
            </div>
            <p v-if="activeTicket.related_title" class="mt-2 text-[11px] text-secondary">عنوان مرتبط: {{ activeTicket.related_title }}</p>
            <div class="mt-4 max-h-80 space-y-3 overflow-y-auto">
              <article
                v-for="message in activeTicket.messages"
                :key="message.id"
                class="rounded-xl px-3 py-2.5 text-xs leading-6"
                :class="message.is_staff_reply ? 'bg-primary-500/10 text-ink' : 'bg-[var(--surface-1)] text-secondary ring-1 ring-line'"
              >
                <p class="mb-1 text-[10px] font-black text-muted">{{ message.author_username }}</p>
                {{ message.body }}
              </article>
            </div>
            <form v-if="activeTicket.status !== 'closed'" class="mt-4 grid gap-2" @submit.prevent="sendReply">
              <textarea v-model="replyBody" class="ui-field min-h-24 resize-y px-3 py-2 text-sm" placeholder="پاسخ بعدی‌ات را بنویس…" />
              <button type="submit" class="ui-primary-button" :disabled="submitting || !replyBody.trim()">ارسال</button>
            </form>
          </div>
          <p v-else class="rounded-2xl bg-elevated p-5 text-sm text-muted">یک پیام را از فهرست انتخاب کن.</p>
        </div>
      </section>

      <aside class="space-y-4" aria-label="راهنما">
        <section class="ui-surface p-5 sm:p-6">
          <h2 class="text-sm font-black text-ink">برای پاسخ سریع‌تر</h2>
          <ul class="mt-4 space-y-3 text-xs leading-6 text-secondary">
            <li class="flex gap-2"><CinematicIcon name="check-circle" class="mt-1 size-4 shrink-0 text-brand" />برای درخواست فیلم، نام دقیق و سال را بنویس.</li>
            <li class="flex gap-2"><CinematicIcon name="check-circle" class="mt-1 size-4 shrink-0 text-brand" />برای مشکل پخش، نام صفحه و دستگاه را ذکر کن.</li>
            <li class="flex gap-2"><CinematicIcon name="shield-check" class="mt-1 size-4 shrink-0 text-success" />رمز عبور و اطلاعات بانکی را هرگز ارسال نکن.</li>
          </ul>
        </section>
        <NuxtLink to="/about" class="ui-secondary-button w-full">
          آشنایی بیشتر با روایتو<CinematicIcon name="arrow-left" class="size-4" />
        </NuxtLink>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SupportCategory, SupportTicket } from '~/types'

const { isOpen, presetCategory, close } = useSupportModal()
const support = useSupport()
const authStore = useAuthStore()
const notifications = useNotifications()

const categoryOptions: Array<{ value: SupportCategory; label: string; icon: string }> = [
  { value: 'content_request', label: 'فیلم یا سریال', icon: 'film' },
  { value: 'bug', label: 'گزارش مشکل', icon: 'triangle-alert' },
  { value: 'content_fix', label: 'اصلاح اطلاعات', icon: 'pencil-line' },
  { value: 'suggestion', label: 'پیشنهاد', icon: 'sparkles' },
  { value: 'support', label: 'پشتیبانی', icon: 'messages-square' },
  { value: 'cooperation', label: 'همکاری', icon: 'heart' },
]

const category = ref<SupportCategory>('content_request')
const subject = ref('')
const body = ref('')
const submitting = ref(false)
const created = ref<SupportTicket | null>(null)
const copied = ref(false)

watch(isOpen, (open) => {
  if (!open) return
  created.value = null
  subject.value = ''
  body.value = ''
  copied.value = false
  const preset = categoryOptions.find(option => option.value === presetCategory.value)
  category.value = preset?.value || 'content_request'
  nextTick(() => {
    ;(document.querySelector('[data-support-modal] input') as HTMLInputElement | null)?.focus()
  })
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && isOpen.value) close()
}

watch(isOpen, (open) => {
  if (open) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

async function submit() {
  if (!authStore.isAuthenticated) {
    close()
    await navigateTo({ path: '/auth/login', query: { redirect: '/contact' } })
    return
  }
  if (subject.value.trim().length < 4 || body.value.trim().length < 10) {
    notifications.warning('پیام ناقص است', 'موضوع و متن کامل‌تری بنویس.')
    return
  }
  submitting.value = true
  try {
    created.value = await support.create({
      category: category.value,
      subject: subject.value.trim(),
      body: body.value.trim(),
      related_title: '',
      related_year: null,
      related_url: '',
    })
  } catch (cause) {
    notifications.notifyError(cause, 'ارسال پیام انجام نشد.')
  } finally {
    submitting.value = false
  }
}

async function copyCode() {
  const code = created.value?.tracking_code
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    copied.value = true
    notifications.success('کد پیگیری کپی شد')
  } catch {
    notifications.error('کپی نشد', 'کد را دستی انتخاب کن.')
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="support-modal">
      <div
        v-if="isOpen"
        class="fixed inset-0 z-[96] flex items-end justify-center sm:items-center sm:p-6"
        role="dialog"
        aria-modal="true"
        aria-label="ارتباط سریع با پشتیبانی روایتو"
      >
        <div class="absolute inset-0 bg-black/60 backdrop-blur-md" aria-hidden="true" @click="close" />

        <div class="support-aurora pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
          <span class="support-aurora__blob support-aurora__blob--a" />
          <span class="support-aurora__blob support-aurora__blob--b" />
        </div>

        <section
          data-support-modal
          class="relative w-full max-w-lg overflow-hidden rounded-t-3xl border border-white/12 bg-surface/92 shadow-[0_30px_80px_rgba(0,0,0,.55)] backdrop-blur-2xl sm:rounded-3xl"
        >
          <header class="flex items-center justify-between gap-3 border-b border-white/8 px-5 py-4">
            <div class="flex items-center gap-3">
              <span class="grid size-10 place-items-center rounded-2xl bg-gradient-to-br from-primary-400/30 to-crimson/25 text-brand ring-1 ring-white/12">
                <CinematicIcon name="wand-sparkles" class="size-5" />
              </span>
              <div>
                <h2 class="text-sm font-black text-ink">پیام به روایتو</h2>
                <p class="text-[11px] text-muted">معمولاً کمتر از یک روز پاسخ می‌دهیم</p>
              </div>
            </div>
            <button type="button" class="grid size-9 place-items-center rounded-xl text-secondary transition hover:bg-white/8 hover:text-ink active:scale-90" aria-label="بستن" @click="close">
              <CinematicIcon name="x" class="size-4.5" />
            </button>
          </header>

          <Transition name="support-step" mode="out-in">
            <div v-if="created" key="done" class="px-6 py-9 text-center">
              <span class="support-done mx-auto grid size-16 place-items-center rounded-full bg-success/15 text-success ring-1 ring-success/30">
                <CinematicIcon name="circle-check" class="size-8" />
              </span>
              <h3 class="mt-4 text-lg font-black text-ink">پیامت ثبت شد!</h3>
              <p class="mt-1 text-xs leading-6 text-muted">این کد را نگه دار تا در «پیام‌های من» گفتگو را پی بگیری.</p>
              <button
                type="button"
                dir="ltr"
                class="mx-auto mt-4 inline-flex min-h-11 items-center gap-2 rounded-2xl bg-elevated px-5 font-latin text-sm font-black tracking-wider text-brand ring-1 ring-primary-500/25 transition hover:bg-primary-500/10 active:scale-95"
                @click="copyCode"
              >
                {{ created.tracking_code }}
                <CinematicIcon :name="copied ? 'check' : 'share-2'" class="size-4" />
              </button>
              <div class="mt-6 flex justify-center gap-2">
                <NuxtLink to="/contact" class="ui-secondary-button min-h-11" @click="close">گفتگوها</NuxtLink>
                <button type="button" class="ui-primary-button min-h-11" @click="close">تمام</button>
              </div>
            </div>

            <form v-else key="compose" class="grid gap-4 px-5 py-5" @submit.prevent="submit">
              <p class="text-xs font-bold text-secondary">چطور کمک کنیم؟</p>
              <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <button
                  v-for="option in categoryOptions"
                  :key="option.value"
                  type="button"
                  class="support-chip group"
                  :class="{ 'is-active': category === option.value }"
                  :aria-pressed="category === option.value"
                  @click="category = option.value"
                >
                  <CinematicIcon :name="option.icon" class="size-4.5 transition-transform group-hover:scale-110" />
                  <span>{{ option.label }}</span>
                </button>
              </div>

              <input
                v-model="subject"
                class="ui-field px-4 text-sm"
                required
                minlength="4"
                placeholder="موضوع را در یک خط بنویس…"
                aria-label="موضوع پیام"
              >
              <textarea
                v-model="body"
                class="ui-field min-h-28 resize-y px-4 py-3 text-sm leading-7"
                required
                minlength="10"
                placeholder="جزئیات… (نام فیلم، صفحه مشکل، دستگاه)"
                aria-label="متن پیام"
              />

              <button type="submit" class="ui-primary-button min-h-11 w-full" :disabled="submitting">
                {{ submitting ? 'در حال ارسال…' : 'ارسال سریع' }}
                <CinematicIcon name="zap" class="size-4" />
              </button>
              <div class="flex items-center justify-between text-[11px]">
                <NuxtLink to="/contact" class="font-bold text-brand hover:underline" @click="close">گفتگوی کامل‌تر</NuxtLink>
                <NuxtLink v-if="!authStore.isAuthenticated" to="/auth/login?redirect=/contact" class="font-bold text-secondary hover:text-ink" @click="close">ورود به حساب</NuxtLink>
                <a v-else href="https://t.me/revayato" target="_blank" rel="noopener noreferrer" class="font-bold text-secondary hover:text-ink">@revayato در تلگرام</a>
              </div>
            </form>
          </Transition>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.support-aurora__blob {
  position: absolute;
  width: 22rem;
  height: 22rem;
  border-radius: 9999px;
  filter: blur(90px);
  opacity: .35;
  animation: support-blob-drift 9s ease-in-out infinite alternate;
}

.support-aurora__blob--a {
  inset-inline-start: -6rem;
  top: -7rem;
  background: radial-gradient(circle, var(--theme-accent-primary) 0%, transparent 70%);
}

.support-aurora__blob--b {
  inset-inline-end: -7rem;
  bottom: -8rem;
  background: radial-gradient(circle, var(--theme-accent-crimson, #b04848) 0%, transparent 70%);
  animation-delay: -4.5s;
}

@keyframes support-blob-drift {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(2rem, 1.5rem, 0) scale(1.18); }
}

.support-chip {
  display: flex;
  min-height: 3rem;
  align-items: center;
  justify-content: center;
  gap: .45rem;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 1rem;
  background: rgb(255 255 255 / 4%);
  color: var(--theme-text-secondary);
  font-size: .72rem;
  font-weight: 800;
  transition: all 160ms ease;
}

.support-chip:hover { border-color: rgb(255 255 255 / 20%); color: var(--theme-text-primary); }

.support-chip.is-active {
  border-color: transparent;
  background:
    linear-gradient(var(--theme-bg-surface), var(--theme-bg-surface)) padding-box,
    linear-gradient(120deg, var(--theme-accent-primary), var(--theme-accent-crimson, #b04848)) border-box;
  color: var(--theme-accent-primary);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--theme-accent-primary) 24%, transparent);
}

.support-done { animation: support-pop 420ms cubic-bezier(.2, 1.4, .4, 1) both; }
@keyframes support-pop { from { transform: scale(.4); opacity: 0; } }

.support-step-enter-active,
.support-step-leave-active { transition: opacity 160ms ease, transform 180ms ease; }
.support-step-enter-from { opacity: 0; transform: translateY(.6rem); }
.support-step-leave-to { opacity: 0; transform: translateY(-.4rem); }

.support-modal-enter-active,
.support-modal-leave-active { transition: opacity 200ms ease; }
.support-modal-enter-from,
.support-modal-leave-to { opacity: 0; }
.support-modal-enter-active section { transition: transform 260ms cubic-bezier(.2, 1.1, .3, 1); }
.support-modal-enter-from section { transform: translateY(2rem) scale(.97); }
.support-modal-leave-to section { transform: translateY(1rem) scale(.98); }

@media (prefers-reduced-motion: reduce) {
  .support-aurora__blob { animation: none; }
}
</style>

<script setup lang="ts">
/**
 * What a viewer abroad sees instead of a player that never starts.
 *
 * The playback CDNs answer only Iranian addresses and drop everything else
 * without a word, so the failure the viewer would otherwise meet is the
 * player's own startup watchdog — a timeout that describes the symptom and not
 * one thing they could act on. This says the cause and what to do about it.
 *
 * It explains rather than blocks: it is dismissible, playback is never stopped,
 * and a viewer who believes the verdict is wrong can close it and try. The
 * country is only ever shown when an edge actually resolved one.
 */
const props = defineProps<{
  open: boolean
  /** Persian country name, or '' when nothing resolved one. */
  countryName?: string
}>()

const emit = defineEmits<{ close: [] }>()

const panel = useTemplateRef<HTMLElement>('panel')
const dismissButton = useTemplateRef<HTMLButtonElement>('dismissButton')
let previouslyFocused: HTMLElement | null = null

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function close() {
  emit('close')
}

function reload() {
  if (import.meta.client) window.location.reload()
}

function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !panel.value) return
  const controls = [...panel.value.querySelectorAll<HTMLElement>(focusableSelector)]
    .filter(control => control.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)
  if (!first || !last) {
    event.preventDefault()
    panel.value.focus()
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.open, async (open) => {
  if (!import.meta.client) return
  if (!open) {
    previouslyFocused?.focus()
    previouslyFocused = null
    return
  }
  previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
  await nextTick()
  dismissButton.value?.focus()
}, { immediate: true })

onKeyStroke('Escape', () => {
  if (props.open) close()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="region-modal">
      <div
        v-if="open"
        class="region-modal theme-media-dark"
        role="presentation"
        dir="rtl"
        lang="fa"
        @mousedown.self="close"
      >
        <section
          ref="panel"
          tabindex="-1"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="region-modal-title"
          aria-describedby="region-modal-reason"
          class="region-modal__panel"
          @keydown="trapFocus"
        >
          <header class="region-modal__head">
            <span class="region-modal__icon" aria-hidden="true">
              <CinematicIcon name="globe" class="size-6" />
            </span>
            <div class="min-w-0 flex-1">
              <h2 id="region-modal-title" class="region-modal__title">
                پخش آنلاین فقط با آی‌پی ایران
              </h2>
              <p v-if="countryName" class="region-modal__origin">
                اتصال شما از <strong>{{ countryName }}</strong> شناسایی شد.
              </p>
            </div>
          </header>

          <p id="region-modal-reason" class="region-modal__reason">
            سرورهای پخش روایتو فقط به کاربران داخل ایران پاسخ می‌دهند. با آی‌پی خارج از ایران، ویدیو
            اصلاً شروع نمی‌شود و پلیر بعد از چند ثانیه پیام خطا نشان می‌دهد — مشکل از فیلم یا لینک نیست.
          </p>

          <!-- Numbered because it is a sequence: each step only helps once the
               one before it is done, and the last is what actually reloads. -->
          <ol class="region-modal__steps">
            <li>وی‌پی‌ان یا پروکسی را خاموش کن.</li>
            <li>اگر برای دسترسی به اینترنت به وی‌پی‌ان نیاز داری، سرورش را روی <strong>ایران</strong> بگذار.</li>
            <li>صفحه را تازه کن تا پخش از همان‌جا ادامه پیدا کند.</li>
          </ol>

          <p class="region-modal__note">
            دانلود مستقیم هم از همین سرورها انجام می‌شود، پس آن هم به آی‌پی ایران نیاز دارد.
          </p>

          <div class="region-modal__actions">
            <button type="button" class="region-modal__primary" @click="reload">
              <CinematicIcon name="refresh" class="size-5" />
              آی‌پی را عوض کردم، صفحه را تازه کن
            </button>
            <button
              ref="dismissButton"
              type="button"
              class="region-modal__dismiss"
              @click="close"
            >
              بستن و به‌هرحال امتحان می‌کنم
            </button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.region-modal {
  position: fixed;
  inset: 0;
  z-index: 95;
  display: flex;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgb(2 6 5 / 86%);
}

.region-modal__panel {
  width: min(100%, 30rem);
  max-height: calc(100dvh - 2rem);
  overflow-y: auto;
  cursor: default;
  padding: 1.35rem;
  border: 1px solid rgb(255 255 255 / 11%);
  border-radius: 1.5rem;
  color: #e6ebe9;
  background:
    radial-gradient(circle at 85% -15%, rgb(var(--media-accent-rgb, 176 228 204) / 20%), transparent 45%),
    #07100d;
  box-shadow: none;
  outline: none;
  overscroll-behavior: contain;
}

.region-modal__head {
  display: flex;
  align-items: flex-start;
  gap: .75rem;
}

.region-modal__icon {
  display: grid;
  width: 2.9rem;
  height: 2.9rem;
  flex: none;
  place-items: center;
  border-radius: .9rem;
  color: #050807;
  background: var(--media-accent, #b0e4cc);
}

.region-modal__title {
  font-size: 1.05rem;
  font-weight: 900;
  line-height: 1.7;
}

.region-modal__origin {
  margin-top: .2rem;
  color: #a7b2ad;
  font-size: .8rem;
  font-weight: 700;
}

.region-modal__origin strong {
  color: var(--media-accent, #b0e4cc);
}

.region-modal__reason {
  margin-top: .95rem;
  color: #c2ccc8;
  font-size: .82rem;
  line-height: 2;
}

.region-modal__steps {
  margin-top: .9rem;
  display: grid;
  gap: .5rem;
  padding: .85rem 1rem;
  counter-reset: region-step;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 1rem;
  background: rgb(255 255 255 / 4%);
  list-style: none;
}

.region-modal__steps li {
  position: relative;
  padding-inline-start: 1.9rem;
  counter-increment: region-step;
  color: #d5ddda;
  font-size: .8rem;
  line-height: 1.95;
}

.region-modal__steps li::before {
  content: counter(region-step);
  position: absolute;
  inset-inline-start: 0;
  top: .3rem;
  display: grid;
  width: 1.35rem;
  height: 1.35rem;
  place-items: center;
  border-radius: 50%;
  color: #050807;
  background: var(--media-accent, #b0e4cc);
  font-size: 0.75rem;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
}

.region-modal__note {
  margin-top: .75rem;
  color: #7a8681;
  font-size: .72rem;
  line-height: 1.9;
}

.region-modal__actions {
  margin-top: 1.15rem;
  display: grid;
  gap: .6rem;
}

.region-modal__primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  padding: .8rem 1.1rem;
  border-radius: .9rem;
  color: #050807;
  background: var(--media-accent, #b0e4cc);
  font-size: .85rem;
  font-weight: 900;
  transition: filter .15s ease;
}

.region-modal__primary:hover {
  filter: brightness(1.08);
}

.region-modal__dismiss {
  padding: .5rem;
  color: #7a8681;
  font-size: .75rem;
  font-weight: 700;
  transition: color .15s ease;
}

.region-modal__dismiss:hover {
  color: #c2ccc8;
}

.region-modal__primary:focus-visible,
.region-modal__dismiss:focus-visible {
  outline: 2px solid var(--media-accent, #b0e4cc);
  outline-offset: 2px;
}

.region-modal-enter-active,
.region-modal-leave-active {
  transition: opacity .18s ease;
}

.region-modal-enter-active .region-modal__panel,
.region-modal-leave-active .region-modal__panel {
  transition: transform .2s ease, opacity .18s ease;
}

.region-modal-enter-from,
.region-modal-leave-to {
  opacity: 0;
}

.region-modal-enter-from .region-modal__panel,
.region-modal-leave-to .region-modal__panel {
  opacity: 0;
  transform: translateY(1rem) scale(.985);
}

@media (prefers-reduced-motion: reduce) {
  .region-modal-enter-active,
  .region-modal-leave-active,
  .region-modal-enter-active .region-modal__panel,
  .region-modal-leave-active .region-modal__panel {
    transition: none;
  }
}
</style>

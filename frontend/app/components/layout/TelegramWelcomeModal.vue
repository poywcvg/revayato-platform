<script setup lang="ts">
const STORAGE_KEY = 'revayato-telegram-invite-seen-v1'
const TELEGRAM_URL = 'https://t.me/revayato'
const open = ref(false)
const dialog = useTemplateRef<HTMLElement>('dialog')
const joinButton = useTemplateRef<HTMLAnchorElement>('joinButton')
const focusableSelector = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
let previouslyFocused: HTMLElement | null = null
let previousBodyOverflow = ''

function rememberInvite() {
  try {
    localStorage.setItem(STORAGE_KEY, '1')
  } catch {
    // Storage can be unavailable in strict privacy modes; the dialog still works.
  }
}

function close() {
  rememberInvite()
  open.value = false
}

function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !dialog.value) return

  const controls = [...dialog.value.querySelectorAll<HTMLElement>(focusableSelector)]
    .filter(control => control.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)

  if (!first || !last) {
    event.preventDefault()
    dialog.value.focus()
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(() => {
  try {
    if (localStorage.getItem(STORAGE_KEY) === '1') return
  } catch {
    // If storage cannot be read, show the invite without breaking the page.
  }

  open.value = true
})

watch(open, async (isOpen) => {
  if (!import.meta.client) return

  if (isOpen) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    await nextTick()
    joinButton.value?.focus()
  } else {
    document.body.style.overflow = previousBodyOverflow
    previouslyFocused?.focus()
    previouslyFocused = null
  }
})

onKeyStroke('Escape', () => {
  if (open.value) close()
})

onBeforeUnmount(() => {
  if (import.meta.client && open.value) document.body.style.overflow = previousBodyOverflow
})
</script>

<template>
  <Teleport to="body">
    <Transition name="telegram-welcome">
      <div
        v-if="open"
        class="telegram-welcome"
        role="presentation"
        @click.self="close"
      >
        <section
          ref="dialog"
          class="telegram-welcome__dialog"
          tabindex="-1"
          role="dialog"
          aria-modal="true"
          aria-labelledby="telegram-welcome-title"
          aria-describedby="telegram-welcome-description"
          @keydown="trapFocus"
        >
          <button
            type="button"
            class="telegram-welcome__close"
            aria-label="بستن دعوت عضویت در تلگرام"
            @click="close"
          >
            <CinematicIcon name="x" class="size-5" />
          </button>

          <div class="telegram-welcome__hero" aria-hidden="true">
            <span class="telegram-welcome__glow" />
            <span class="telegram-welcome__logo">
              <svg viewBox="0 0 32 32" fill="currentColor">
                <path d="M16 0a16 16 0 1 0 0 32 16 16 0 0 0 0-32Zm7.84 10.72-2.4 11.32c-.18.8-.66 1-1.33.62l-3.66-2.7-1.76 1.7c-.2.2-.36.36-.74.36l.27-3.72L21 12.17c.3-.27-.06-.41-.46-.15l-8.39 5.28-3.61-1.13c-.78-.24-.8-.78.17-1.16l14.11-5.44c.66-.25 1.23.14 1.02 1.15Z" />
              </svg>
            </span>
          </div>

          <div class="telegram-welcome__content">
            <p class="telegram-welcome__eyebrow">کانال رسمی روایتو</p>
            <h2 id="telegram-welcome-title">از تازه‌های روایتو باخبر شو</h2>
            <p id="telegram-welcome-description">
              برای اطلاع از اضافه‌شدن فیلم‌ها و سریال‌های جدید، به کانال تلگرام روایتو بپیوند.
            </p>

            <div class="telegram-welcome__actions">
              <a
                ref="joinButton"
                :href="TELEGRAM_URL"
                target="_blank"
                rel="noopener noreferrer"
                class="telegram-welcome__join"
                @click="close"
              >
                عضویت در کانال تلگرام
                <CinematicIcon name="arrow-up-right" class="size-4.5" />
              </a>
              <button type="button" class="telegram-welcome__later" @click="close">
                فعلاً نه
              </button>
            </div>

            <span class="telegram-welcome__handle" dir="ltr">@revayato</span>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.telegram-welcome {
  position: fixed;
  z-index: 130;
  inset: 0;
  display: flex;
  padding: max(1rem, env(safe-area-inset-top)) 1rem max(1rem, env(safe-area-inset-bottom));
  align-items: flex-end;
  justify-content: center;
  background: var(--theme-overlay-backdrop);
  backdrop-filter: blur(8px);
}

.telegram-welcome__dialog {
  position: relative;
  width: min(100%, 28rem);
  max-height: calc(100dvh - 2rem - env(safe-area-inset-top) - env(safe-area-inset-bottom));
  overflow-y: auto;
  border: 1px solid color-mix(in srgb, #2aabee 24%, var(--theme-border));
  border-radius: 1.75rem;
  background: var(--theme-bg-surface);
  color: var(--theme-text-primary);
  box-shadow: 0 28px 80px rgb(0 0 0 / 58%);
  outline: none;
}

.telegram-welcome__close {
  position: absolute;
  z-index: 2;
  top: .75rem;
  left: .75rem;
  display: grid;
  width: 2.75rem;
  height: 2.75rem;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 12%);
  border-radius: 9999px;
  background: rgb(0 0 0 / 24%);
  color: rgb(255 255 255 / 78%);
  backdrop-filter: blur(10px);
  transition: background-color 160ms ease, color 160ms ease, transform 160ms ease;
}

.telegram-welcome__close:hover {
  background: rgb(255 255 255 / 12%);
  color: #fff;
  transform: rotate(4deg);
}

.telegram-welcome__hero {
  position: relative;
  display: grid;
  min-height: 10.5rem;
  place-items: center;
  overflow: hidden;
  border-radius: 1.7rem 1.7rem 0 0;
  background:
    radial-gradient(circle at 50% 20%, rgb(125 211 252 / 28%), transparent 48%),
    linear-gradient(145deg, #102d3d, #151c22 64%, #0d0d0d);
}

.telegram-welcome__hero::before,
.telegram-welcome__hero::after {
  position: absolute;
  width: 9rem;
  height: 9rem;
  border: 1px solid rgb(42 171 238 / 13%);
  border-radius: 50%;
  content: '';
}

.telegram-welcome__hero::after {
  width: 13rem;
  height: 13rem;
}

.telegram-welcome__glow {
  position: absolute;
  width: 7.5rem;
  height: 7.5rem;
  border-radius: 50%;
  background: #2aabee;
  filter: blur(44px);
  opacity: .3;
}

.telegram-welcome__logo {
  position: relative;
  display: grid;
  width: 5.25rem;
  height: 5.25rem;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 22%);
  border-radius: 1.75rem;
  background: linear-gradient(145deg, #39b8f3, #168ac7);
  color: #fff;
  box-shadow: 0 18px 44px rgb(3 110 167 / 38%);
  transform: rotate(-3deg);
}

.telegram-welcome__logo svg {
  width: 3.35rem;
  height: 3.35rem;
}

.telegram-welcome__content {
  padding: 1.5rem;
  text-align: center;
}

.telegram-welcome__eyebrow {
  margin: 0 0 .35rem;
  color: #63c8f6;
  font-size: .72rem;
  font-weight: 900;
}

.telegram-welcome__content h2 {
  margin: 0;
  font-size: clamp(1.25rem, 5vw, 1.55rem);
  font-weight: 900;
  letter-spacing: -.035em;
}

.telegram-welcome__content > p:not(.telegram-welcome__eyebrow) {
  max-width: 23rem;
  margin: .7rem auto 0;
  color: var(--theme-text-secondary);
  font-size: .86rem;
  line-height: 1.9;
}

.telegram-welcome__actions {
  display: grid;
  margin-top: 1.35rem;
  gap: .55rem;
}

.telegram-welcome__join,
.telegram-welcome__later {
  display: inline-flex;
  min-height: 3.15rem;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  border-radius: .85rem;
  font-size: .82rem;
  font-weight: 900;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, transform 160ms ease;
}

.telegram-welcome__join {
  background: #2aabee;
  color: #04131b;
}

.telegram-welcome__join:hover {
  background: #55bdf2;
  transform: translateY(-1px);
}

.telegram-welcome__later {
  border: 1px solid var(--theme-border);
  background: var(--theme-bg-elevated);
  color: var(--theme-text-secondary);
}

.telegram-welcome__later:hover {
  border-color: var(--theme-border-strong);
  background: var(--theme-surface-hover);
  color: var(--theme-text-primary);
}

.telegram-welcome__handle {
  display: block;
  margin-top: .9rem;
  color: var(--theme-text-muted);
  font-family: var(--font-latin-ui);
  font-size: .68rem;
  font-weight: 700;
}

.telegram-welcome-enter-active,
.telegram-welcome-leave-active {
  transition: opacity 200ms ease;
}

.telegram-welcome-enter-active .telegram-welcome__dialog,
.telegram-welcome-leave-active .telegram-welcome__dialog {
  transition: transform 220ms cubic-bezier(.2, .8, .2, 1), opacity 180ms ease;
}

.telegram-welcome-enter-from,
.telegram-welcome-leave-to {
  opacity: 0;
}

.telegram-welcome-enter-from .telegram-welcome__dialog,
.telegram-welcome-leave-to .telegram-welcome__dialog {
  opacity: 0;
  transform: translateY(1.5rem) scale(.97);
}

@media (min-width: 640px) {
  .telegram-welcome {
    align-items: center;
  }
}

@media (max-width: 639px) {
  .telegram-welcome {
    padding-inline: .5rem;
    padding-bottom: max(.5rem, env(safe-area-inset-bottom));
  }

  .telegram-welcome__dialog {
    width: 100%;
    border-radius: 1.5rem;
  }

  .telegram-welcome__hero {
    min-height: 8.75rem;
    border-radius: 1.45rem 1.45rem 0 0;
  }

  .telegram-welcome__logo {
    width: 4.5rem;
    height: 4.5rem;
    border-radius: 1.4rem;
  }

  .telegram-welcome__logo svg {
    width: 2.9rem;
    height: 2.9rem;
  }

  .telegram-welcome__content {
    padding: 1.25rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .telegram-welcome-enter-active,
  .telegram-welcome-leave-active,
  .telegram-welcome-enter-active .telegram-welcome__dialog,
  .telegram-welcome-leave-active .telegram-welcome__dialog {
    transition: none;
  }
}
</style>

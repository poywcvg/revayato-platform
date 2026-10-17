<script setup lang="ts">
// A small, quiet invite to the Android app. It never covers the page on first
// visit (the Telegram welcome goes first), never shows on iOS (no app there) or
// on /app itself, and one tap on × keeps it away for two weeks.
const DISMISS_KEY = 'revayato-app-invite-dismissed-at'
const TELEGRAM_SEEN_KEY = 'revayato-telegram-invite-seen-v1'
const DISMISS_DAYS = 14
const AFTER_VISIT_DAYS = 30
const SHOW_DELAY_MS = 4000

const route = useRoute()
const visible = ref(false)
const isAndroid = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function hideFor(days: number) {
  visible.value = false
  try {
    // Stored as the moment the invite may come back.
    localStorage.setItem(DISMISS_KEY, String(Date.now() + days * 86_400_000))
  } catch {
    // Without storage it simply stays hidden for this page view.
  }
}

function eligible(): boolean {
  if (route.path.startsWith('/app')) return false
  const ua = navigator.userAgent || ''
  const isIos = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1)
  if (isIos) return false
  if (readStorage(TELEGRAM_SEEN_KEY) !== '1') return false
  const until = Number(readStorage(DISMISS_KEY) || 0)
  return !(until && Date.now() < until)
}

function evaluate() {
  clearTimeout(timer)
  if (!eligible()) {
    visible.value = false
    return
  }
  if (visible.value) return
  timer = setTimeout(() => {
    visible.value = eligible()
  }, SHOW_DELAY_MS)
}

onMounted(() => {
  isAndroid.value = /Android/i.test(navigator.userAgent || '')
  evaluate()
})

// Re-check on navigation: the Telegram welcome may have been closed since.
watch(() => route.path, () => evaluate())

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <Transition name="app-fab">
    <div v-if="visible" class="app-fab" role="complementary" aria-label="اپلیکیشن اندروید روایتو">
      <NuxtLink to="/app" class="app-fab__link" @click="hideFor(AFTER_VISIT_DAYS)">
        <span class="app-fab__icon" aria-hidden="true">
          <CinematicIcon name="smartphone" class="size-4" />
        </span>
        <span class="app-fab__text">
          <strong>{{ isAndroid ? 'نصب اپ روایتو' : 'اپ اندروید روایتو' }}</strong>
          <small>{{ isAndroid ? 'سریع‌تر، با دانلود آفلاین' : 'دانلود آفلاین و تماشای گروهی' }}</small>
        </span>
      </NuxtLink>
      <button type="button" class="app-fab__close" aria-label="بستن دعوت به نصب اپ" @click="hideFor(DISMISS_DAYS)">
        <CinematicIcon name="x" class="size-3.5" />
      </button>
    </div>
  </Transition>
</template>

<style scoped>
.app-fab {
  position: fixed;
  z-index: 44;
  inset-inline-start: max(1rem, env(safe-area-inset-left), env(safe-area-inset-right));
  bottom: calc(1.25rem + env(safe-area-inset-bottom));
  display: flex;
  max-width: calc(100vw - 6rem);
  align-items: center;
  gap: .15rem;
  border: 1px solid color-mix(in srgb, var(--theme-accent-primary) 30%, var(--theme-border));
  border-radius: 1rem;
  background: var(--theme-bg-elevated);
  padding: .3rem;
  color: var(--theme-text-primary);
  box-shadow: none;
}

@media (max-width: 1023px) {
  .app-fab {
    bottom: calc(var(--mobile-bottom-nav-height) + .75rem + env(safe-area-inset-bottom));
  }
}

.app-fab__link {
  display: flex;
  min-width: 0;
  min-height: 2.75rem;
  align-items: center;
  gap: .55rem;
  border-radius: .75rem;
  padding-inline: .3rem .5rem;
  color: inherit;
  text-decoration: none;
}

.app-fab__link:hover { background: color-mix(in srgb, var(--theme-accent-primary) 10%, transparent); }

.app-fab__link:focus-visible,
.app-fab__close:focus-visible {
  outline: 2px solid var(--theme-accent-primary);
  outline-offset: 2px;
}

.app-fab__icon {
  display: grid;
  width: 2.25rem;
  height: 2.25rem;
  flex: none;
  place-items: center;
  border-radius: .7rem;
  background: var(--theme-accent-primary);
  color: var(--theme-on-accent);
}

.app-fab__text {
  display: grid;
  min-width: 0;
  line-height: 1.35;
}

.app-fab__text strong {
  overflow: hidden;
  font-size: .8125rem;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-fab__text small {
  overflow: hidden;
  color: var(--theme-text-secondary);
  font-size: .6875rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-fab__close {
  display: grid;
  width: 2rem;
  height: 2.75rem;
  flex: none;
  place-items: center;
  border-radius: .6rem;
  color: var(--theme-text-secondary);
}

.app-fab__close:hover {
  background: color-mix(in srgb, var(--theme-text-primary) 8%, transparent);
  color: var(--theme-text-primary);
}

.app-fab-enter-active,
.app-fab-leave-active { transition: opacity 160ms ease, transform 160ms ease; }
.app-fab-enter-from,
.app-fab-leave-to { opacity: 0; transform: translateY(.5rem); }

@media (prefers-reduced-motion: reduce) {
  .app-fab-enter-active,
  .app-fab-leave-active { transition: none; }
}
</style>

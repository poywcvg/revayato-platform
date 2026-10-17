<script setup lang="ts">
const chat = useCommunityChat()
const authStore = useAuthStore()
const route = useRoute()

const draft = ref('')
const listRef = useTemplateRef<HTMLElement>('listRef')
const panelRef = useTemplateRef<HTMLElement>('panelRef')
const MAX_LEN = 500

const isPlayerRoute = computed(() =>
  route.path.startsWith('/watch/') || route.path.startsWith('/watch-party/'),
)

function initial(name: string) {
  return (name || '').trim().charAt(0) || '؟'
}

function formatTime(value: string) {
  try {
    return new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
  } catch {
    return ''
  }
}

async function submit() {
  const ok = await chat.send(draft.value)
  if (ok) {
    draft.value = ''
    scrollToEnd(true)
  }
}

function loginRedirect() {
  return `/auth/login?redirect=${encodeURIComponent(route.fullPath || '/')}`
}

function scrollToEnd(smooth = false) {
  nextTick(() => {
    listRef.value?.scrollTo({
      top: listRef.value.scrollHeight,
      behavior: smooth ? 'smooth' : 'auto',
    })
  })
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && chat.isOpen.value) chat.close()
}

watch(() => chat.isOpen.value, (open) => {
  if (open) {
    scrollToEnd()
    nextTick(() => panelRef.value?.focus())
  }
})

watch(() => chat.messages.value.length, () => {
  if (chat.isOpen.value) scrollToEnd(true)
})

onMounted(() => window.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div v-if="!isPlayerRoute" class="community-dock">
    <!-- Invite bubble: one warm nudge per day, never blocking -->
    <Transition name="community-invite">
      <div
        v-if="chat.inviteVisible.value && !chat.isOpen.value"
        class="community-invite"
        role="status"
      >
        <span class="community-invite__dot" aria-hidden="true" />
        <p class="community-invite__text">بچه‌های فیلم‌باز اینجان؛ بیا تو گفتگو!</p>
        <button
          type="button"
          class="community-invite__close"
          aria-label="بستن دعوت"
          @click="chat.dismissInvite()"
        >
          <CinematicIcon name="x" class="size-3.5" />
        </button>
      </div>
    </Transition>

    <!-- Floating entry: left side, stacked above scroll-to-top, clear of nav -->
    <button
      v-if="!chat.isOpen.value"
      type="button"
      class="community-fab"
      aria-label="باز کردن گفتگوی جمعی"
      @click="chat.open()"
    >
      <span class="community-fab__pulse" aria-hidden="true" />
      <CinematicIcon name="comments" class="size-5" />
      <span class="community-fab__label">گفتگو</span>
      <span class="community-fab__live" aria-hidden="true"><span />زنده</span>
      <span v-if="chat.unread.value" class="community-fab__badge">{{ chat.unread.value }}</span>
    </button>

    <!-- Panel -->
    <Transition name="community-panel">
      <section
        v-if="chat.isOpen.value"
        ref="panelRef"
        tabindex="-1"
        class="community-panel"
        role="dialog"
        aria-modal="false"
        aria-label="گفتگوی جمعی روایتو"
      >
        <header class="community-panel__header">
          <span class="community-panel__avatar" aria-hidden="true">
            <CinematicIcon name="comments" class="size-5" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 class="community-panel__title">گفتگوی جمعی</h2>
            <p class="community-panel__sub">
              <span class="community-panel__live-dot" aria-hidden="true" />
              {{ chat.messages.value.length ? `${chat.messages.value.length} پیام آخر` : 'همین حالا شروع کن' }} · با احترام، بدون اسپویل
            </p>
          </div>
          <button
            type="button"
            class="community-panel__icon-btn"
            aria-label="تازه‌سازی گفتگو"
            :disabled="chat.pending.value"
            @click="chat.refresh()"
          >
            <CinematicIcon name="refresh" class="size-4" :class="chat.pending.value && 'animate-spin'" />
          </button>
          <button
            type="button"
            class="community-panel__icon-btn"
            aria-label="بستن گفتگو"
            @click="chat.close()"
          >
            <CinematicIcon name="x" class="size-4" />
          </button>
        </header>

        <div
          ref="listRef"
          class="community-panel__list"
          aria-live="polite"
        >
          <div v-if="chat.pending.value && !chat.messages.value.length" class="community-panel__state">
            <span class="community-panel__spinner" aria-hidden="true" />
            <p>در حال وصل شدن به جمع…</p>
          </div>
          <div v-else-if="!chat.messages.value.length" class="community-panel__state">
            <span class="community-panel__empty-icon" aria-hidden="true">
              <CinematicIcon name="comments" class="size-6" />
            </span>
            <p class="font-black">هنوز حرفی زده نشده</p>
            <p class="community-panel__hint">اولین سلام را تو بگو؛ درباره چیزی که دیشب دیدی.</p>
          </div>
          <article
            v-for="msg in chat.messages.value"
            v-else
            :key="msg.id"
            class="community-msg"
          >
            <span class="community-msg__avatar" aria-hidden="true">{{ initial(msg.display_name || msg.username) }}</span>
            <div class="min-w-0 flex-1">
              <div class="community-msg__meta">
                <strong>{{ msg.display_name || msg.username }}</strong>
                <time :datetime="msg.created_at">{{ formatTime(msg.created_at) }}</time>
              </div>
              <p class="community-msg__body">{{ msg.body }}</p>
            </div>
          </article>
        </div>

        <p v-if="chat.error.value" class="community-panel__error" role="alert">{{ chat.error.value }}</p>

        <!-- Auth gate: read for everyone, write only signed-in -->
        <form v-if="authStore.isAuthenticated" class="community-panel__form" @submit.prevent="submit">
          <label class="sr-only" for="community-chat-input">پیام تو</label>
          <input
            id="community-chat-input"
            v-model="draft"
            :maxlength="MAX_LEN"
            autocomplete="off"
            placeholder="نظرت درباره فیلم امشب چیه؟…"
            class="community-panel__input"
            :disabled="chat.sending.value"
          >
          <button
            type="submit"
            class="community-panel__send"
            :disabled="!draft.trim() || chat.sending.value"
            aria-label="ارسال پیام"
          >
            <CinematicIcon v-if="!chat.sending.value" name="send" class="size-4" />
            <span v-else class="community-panel__spinner community-panel__spinner--sm" aria-hidden="true" />
          </button>
        </form>
        <div v-else class="community-panel__gate">
          <CinematicIcon name="login" class="size-4 shrink-0" />
          <p>برای حرف زدن وارد حسابت شو؛ خواندن برای همه آزاد است.</p>
          <NuxtLink :to="loginRedirect()" class="community-panel__login">ورود به حساب</NuxtLink>
        </div>

        <p class="community-panel__rules">مودب باشیم 🙂 بدون توهین، بدون لینک مشکوک، اسپویل را با «اسپویل!» شروع کن.</p>
      </section>
    </Transition>
  </div>
</template>

<style scoped>
.community-dock {
  position: fixed;
  z-index: 45;
  inset-inline: 0;
  bottom: 0;
  pointer-events: none;
}

/* Invite bubble sits right above the FAB, dismisses itself */
.community-invite {
  pointer-events: auto;
  position: absolute;
  left: max(1rem, env(safe-area-inset-left, 0px));
  bottom: calc(8.75rem + env(safe-area-inset-bottom, 0px));
  display: flex;
  max-width: min(19rem, calc(100vw - 2rem));
  align-items: center;
  gap: 0.5rem;
  border: 1px solid color-mix(in srgb, var(--theme-accent-primary) 35%, transparent);
  border-radius: 1rem;
  background: var(--theme-bg-elevated);
  padding: 0.6rem 0.7rem;
  color: var(--theme-text-primary);
  font-size: 0.75rem;
  font-weight: 800;
  box-shadow: 0 8px 28px rgb(0 0 0 / 28%);
}

.community-invite__dot {
  width: 0.5rem;
  height: 0.5rem;
  flex-shrink: 0;
  border-radius: 999px;
  background: #22c55e;
  animation: community-blink 1.6s ease-in-out infinite;
}

.community-invite__text {
  min-width: 0;
  flex: 1;
}

.community-invite__close {
  display: grid;
  width: 1.75rem;
  height: 1.75rem;
  flex-shrink: 0;
  place-items: center;
  border-radius: 0.5rem;
  color: var(--theme-text-secondary);
}

.community-invite__close:hover {
  background: color-mix(in srgb, var(--theme-text-primary) 8%, transparent);
  color: var(--theme-text-primary);
}

/* FAB: high-contrast, labelled, clear of scroll-to-top (left) and nav */
.community-fab {
  pointer-events: auto;
  position: absolute;
  left: max(1rem, env(safe-area-inset-left, 0px));
  bottom: calc(5.25rem + env(safe-area-inset-bottom, 0px));
  display: inline-flex;
  min-height: 3rem;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid transparent;
  border-radius: 1rem;
  background: linear-gradient(135deg, var(--theme-accent-primary), #38bdf8);
  padding-inline: 0.95rem 0.85rem;
  color: #07140f;
  font-size: 0.8125rem;
  font-weight: 900;
  box-shadow: 0 10px 30px rgb(0 0 0 / 32%);
  transition: transform 160ms ease, filter 160ms ease;
}

.community-fab:hover {
  transform: translateY(-1px);
  filter: brightness(1.05);
}

.community-fab:active {
  transform: scale(0.97);
}

.community-fab:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}

.community-fab__pulse {
  position: absolute;
  inset: -3px;
  border-radius: 1.15rem;
  border: 2px solid color-mix(in srgb, var(--theme-accent-primary) 55%, transparent);
  animation: community-pulse 2.2s ease-out infinite;
  pointer-events: none;
}

.community-fab__label {
  white-space: nowrap;
}

.community-fab__live {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  border-radius: 999px;
  background: rgb(0 0 0 / 18%);
  padding: 0.15rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 800;
}

.community-fab__live span {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 999px;
  background: #052e16;
  animation: community-blink 1.4s ease-in-out infinite;
}

.community-fab__badge {
  display: grid;
  min-width: 1.4rem;
  height: 1.4rem;
  place-items: center;
  border-radius: 999px;
  background: #0f172a;
  padding-inline: 0.35rem;
  color: #fff;
  font-size: 0.6875rem;
  font-weight: 900;
}

/* Panel: compact card docked above FAB, never full-screen, never under nav */
.community-panel {
  pointer-events: auto;
  position: absolute;
  left: max(0.75rem, env(safe-area-inset-left, 0px));
  bottom: calc(8.75rem + env(safe-area-inset-bottom, 0px));
  display: flex;
  width: min(24rem, calc(100vw - 1.5rem));
  max-height: min(70dvh, 34rem);
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--theme-border);
  border-radius: 1.25rem;
  background: var(--theme-bg-elevated);
  color: var(--theme-text-primary);
  box-shadow: 0 18px 60px rgb(0 0 0 / 40%);
}

.community-panel__header {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  border-bottom: 1px solid var(--theme-border);
  padding: 0.75rem 0.85rem;
}

.community-panel__avatar {
  display: grid;
  width: 2.4rem;
  height: 2.4rem;
  flex-shrink: 0;
  place-items: center;
  border-radius: 0.85rem;
  background: color-mix(in srgb, var(--theme-accent-primary) 16%, transparent);
  color: var(--theme-accent-primary);
}

.community-panel__title {
  font-size: 0.875rem;
  font-weight: 900;
}

.community-panel__sub {
  display: flex;
  margin-top: 0.15rem;
  align-items: center;
  gap: 0.35rem;
  color: var(--theme-text-secondary);
  font-size: 0.6875rem;
}

.community-panel__live-dot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 999px;
  background: #22c55e;
  animation: community-blink 1.6s ease-in-out infinite;
}

.community-panel__icon-btn {
  display: grid;
  width: 2.25rem;
  height: 2.25rem;
  flex-shrink: 0;
  place-items: center;
  border-radius: 0.7rem;
  color: var(--theme-text-secondary);
}

.community-panel__icon-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--theme-text-primary) 8%, transparent);
  color: var(--theme-text-primary);
}

.community-panel__icon-btn:disabled {
  opacity: 0.45;
}

.community-panel__list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0.75rem 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.community-panel__state {
  display: grid;
  place-items: center;
  gap: 0.6rem;
  padding: 2rem 1rem;
  text-align: center;
  color: var(--theme-text-secondary);
  font-size: 0.75rem;
}

.community-panel__empty-icon {
  display: grid;
  width: 3rem;
  height: 3rem;
  place-items: center;
  border-radius: 1rem;
  background: color-mix(in srgb, var(--theme-accent-primary) 12%, transparent);
  color: var(--theme-accent-primary);
}

.community-panel__hint {
  color: var(--theme-text-secondary);
  font-size: 0.6875rem;
}

.community-panel__spinner {
  width: 1.4rem;
  height: 1.4rem;
  border-radius: 999px;
  border: 2px solid var(--theme-border);
  border-top-color: var(--theme-accent-primary);
  animation: community-spin 0.8s linear infinite;
}

.community-panel__spinner--sm {
  width: 1rem;
  height: 1rem;
}

.community-msg {
  display: flex;
  gap: 0.55rem;
  border-radius: 0.9rem;
  background: color-mix(in srgb, var(--theme-text-primary) 4%, transparent);
  padding: 0.55rem 0.65rem;
}

.community-msg__avatar {
  display: grid;
  width: 1.9rem;
  height: 1.9rem;
  flex-shrink: 0;
  place-items: center;
  border-radius: 0.7rem;
  background: color-mix(in srgb, var(--theme-accent-primary) 18%, transparent);
  color: var(--theme-accent-primary);
  font-size: 0.75rem;
  font-weight: 900;
}

.community-msg__meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.6875rem;
}

.community-msg__meta strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.community-msg__meta time {
  flex-shrink: 0;
  color: var(--theme-text-secondary);
  font-size: 0.625rem;
}

.community-msg__body {
  margin-top: 0.15rem;
  overflow-wrap: anywhere;
  font-size: 0.75rem;
  line-height: 1.7;
}

.community-panel__error {
  margin: 0 0.85rem;
  border-radius: 0.7rem;
  background: color-mix(in srgb, #ef4444 12%, transparent);
  padding: 0.5rem 0.65rem;
  color: #f87171;
  font-size: 0.6875rem;
  font-weight: 700;
}

.community-panel__form {
  display: flex;
  gap: 0.5rem;
  border-top: 1px solid var(--theme-border);
  padding: 0.65rem 0.85rem 0.35rem;
}

.community-panel__input {
  min-width: 0;
  min-height: 2.75rem;
  flex: 1;
  border: 1px solid var(--theme-border);
  border-radius: 0.85rem;
  background: transparent;
  padding-inline: 0.8rem;
  color: inherit;
  font-size: 0.8125rem;
  outline: none;
}

.community-panel__input:focus {
  border-color: color-mix(in srgb, var(--theme-accent-primary) 55%, transparent);
}

.community-panel__send {
  display: grid;
  width: 2.75rem;
  height: 2.75rem;
  flex-shrink: 0;
  place-items: center;
  border-radius: 0.85rem;
  background: var(--theme-accent-primary);
  color: var(--theme-on-accent);
}

.community-panel__send:disabled {
  opacity: 0.45;
}

.community-panel__gate {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border-top: 1px solid var(--theme-border);
  margin: 0;
  padding: 0.75rem 0.85rem 0.25rem;
  font-size: 0.6875rem;
  color: var(--theme-text-secondary);
}

.community-panel__login {
  flex-shrink: 0;
  border-radius: 0.7rem;
  background: var(--theme-accent-primary);
  padding: 0.55rem 0.85rem;
  color: var(--theme-on-accent);
  font-size: 0.6875rem;
  font-weight: 900;
  text-decoration: none;
}

.community-panel__rules {
  padding: 0.45rem 0.85rem calc(0.7rem + env(safe-area-inset-bottom, 0px));
  color: var(--theme-text-secondary);
  font-size: 0.625rem;
  line-height: 1.7;
}

@media (max-width: 1023px) {
  .community-invite {
    bottom: calc(var(--mobile-bottom-nav-height) + 8.25rem + env(safe-area-inset-bottom, 0px));
  }

  .community-fab {
    bottom: calc(var(--mobile-bottom-nav-height) + 4.75rem + env(safe-area-inset-bottom, 0px));
  }

  .community-panel {
    bottom: calc(var(--mobile-bottom-nav-height) + 8.25rem + env(safe-area-inset-bottom, 0px));
    max-height: min(62dvh, 30rem);
  }
}

.community-invite-enter-active,
.community-invite-leave-active,
.community-panel-enter-active,
.community-panel-leave-active {
  transition: opacity 200ms ease, transform 240ms cubic-bezier(0.22, 1, 0.36, 1);
}

.community-invite-enter-from,
.community-invite-leave-to,
.community-panel-enter-from,
.community-panel-leave-to {
  opacity: 0;
  transform: translateY(0.75rem) scale(0.98);
}

@keyframes community-pulse {
  0% { opacity: 0.9; transform: scale(1); }
  70% { opacity: 0; transform: scale(1.12); }
  100% { opacity: 0; transform: scale(1.12); }
}

@keyframes community-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@keyframes community-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .community-fab__pulse,
  .community-panel__live-dot,
  .community-invite__dot,
  .community-fab__live span {
    animation: none;
  }
}
</style>

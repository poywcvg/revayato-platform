<script setup lang="ts">
import type { WatchPartyMessage } from '~/types'

const props = defineProps<{
  message: WatchPartyMessage | null
}>()

const emit = defineEmits<{
  openChat: []
}>()

const visibleMessages = ref<WatchPartyMessage[]>([])
const seenIds = new Set<number>()
const dismissTimers = new Map<number, ReturnType<typeof setTimeout>>()
const DISPLAY_MS = 6500
const MAX_VISIBLE = 3

function initial(name: string) {
  return name.trim().charAt(0) || '؟'
}

function dismiss(id: number) {
  const timer = dismissTimers.get(id)
  if (timer) clearTimeout(timer)
  dismissTimers.delete(id)
  visibleMessages.value = visibleMessages.value.filter(message => message.id !== id)
}

function queueMessage(message: WatchPartyMessage) {
  if (seenIds.has(message.id)) return
  seenIds.add(message.id)
  visibleMessages.value = [...visibleMessages.value, message].slice(-MAX_VISIBLE)

  const timer = setTimeout(() => dismiss(message.id), DISPLAY_MS)
  dismissTimers.set(message.id, timer)
}

function openChat(messageId: number) {
  dismiss(messageId)
  emit('openChat')
}

watch(() => props.message, (message) => {
  if (message) queueMessage(message)
}, { flush: 'post' })

onBeforeUnmount(() => {
  dismissTimers.forEach(timer => clearTimeout(timer))
  dismissTimers.clear()
})
</script>

<template>
  <div
    class="watch-party-message-toasts"
    aria-live="polite"
    aria-atomic="false"
    aria-label="پیام‌های جدید گفت‌وگو"
  >
    <TransitionGroup name="party-message-toast" tag="div" class="relative space-y-2.5">
      <article
        v-for="item in visibleMessages"
        :key="item.id"
        class="party-message-toast group relative overflow-hidden rounded-2xl border border-white/12 bg-[#0b0d0e]/92 text-white shadow-[0_18px_55px_rgba(0,0,0,.55)] backdrop-blur-2xl"
        role="status"
      >
        <button
          type="button"
          class="flex w-full items-start gap-3 p-3.5 pb-4 pl-10 text-right outline-none transition hover:bg-white/[.045] focus-visible:bg-white/[.06]"
          :aria-label="`باز کردن پیام ${item.user.display_name}`"
          @click="openChat(item.id)"
        >
          <span class="relative mt-0.5 shrink-0">
            <img
              v-if="item.user.avatar"
              :src="item.user.avatar"
              :alt="item.user.display_name"
              class="size-10 rounded-xl object-cover ring-1 ring-white/15"
            >
            <span
              v-else
              class="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-primary-500/25 to-info/15 text-sm font-black text-primary-300 ring-1 ring-primary-500/25"
            >
              {{ initial(item.user.display_name) }}
            </span>
            <span class="absolute -bottom-1 -left-1 grid size-5 place-items-center rounded-full bg-primary-500 text-night-950 ring-2 ring-[#0b0d0e]">
              <CinematicIcon name="comment" class="size-2.5" :stroke-width="2.4" />
            </span>
          </span>

          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-2">
              <strong class="min-w-0 flex-1 truncate text-xs font-black text-white">
                {{ item.user.display_name }}
              </strong>
              <span class="inline-flex shrink-0 items-center gap-1 text-[9px] font-bold text-success">
                <span class="size-1.5 animate-pulse rounded-full bg-success" />
                پیام جدید
              </span>
            </span>
            <span class="mt-1.5 line-clamp-2 block break-words text-xs leading-5 text-white/70">
              {{ item.message }}
            </span>
            <span class="mt-2 inline-flex items-center gap-1 text-[10px] font-black text-primary-300 opacity-80 transition group-hover:opacity-100">
              مشاهده در گفت‌وگو
              <CinematicIcon name="arrow-left" class="size-3" />
            </span>
          </span>
        </button>

        <button
          type="button"
          class="absolute left-1.5 top-1.5 grid size-8 place-items-center rounded-lg text-white/30 transition hover:bg-white/10 hover:text-white"
          aria-label="بستن اعلان پیام"
          @click.stop="dismiss(item.id)"
        >
          <CinematicIcon name="x" class="size-3.5" />
        </button>
        <span class="party-message-toast__timer absolute inset-x-0 bottom-0 h-0.5 origin-right bg-gradient-to-l from-primary-500 via-info to-transparent" aria-hidden="true" />
      </article>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.watch-party-message-toasts {
  position: fixed;
  z-index: 70;
  top: max(4.75rem, calc(env(safe-area-inset-top, 0px) + 4rem));
  left: max(.75rem, env(safe-area-inset-left, 0px));
  width: min(22rem, calc(100dvw - 1.5rem));
  pointer-events: none;
}

.party-message-toast {
  pointer-events: auto;
}

.party-message-toast__timer {
  animation: party-message-timer 6.5s linear forwards;
}

.party-message-toast-enter-active,
.party-message-toast-leave-active,
.party-message-toast-move {
  transition: opacity 240ms ease, transform 340ms cubic-bezier(.22, 1, .36, 1);
}

.party-message-toast-enter-from,
.party-message-toast-leave-to {
  opacity: 0;
  transform: translateX(-1rem) scale(.97);
}

.party-message-toast-leave-active {
  position: absolute;
  width: 100%;
}

@keyframes party-message-timer {
  from { transform: scaleX(1); }
  to { transform: scaleX(0); }
}

@media (max-width: 639px) {
  .watch-party-message-toasts {
    top: max(4rem, calc(env(safe-area-inset-top, 0px) + 3.5rem));
  }
}

@media (prefers-reduced-motion: reduce) {
  .party-message-toast-enter-active,
  .party-message-toast-leave-active,
  .party-message-toast-move {
    transition: opacity 120ms ease;
  }

  .party-message-toast-enter-from,
  .party-message-toast-leave-to {
    transform: none;
  }
}
</style>

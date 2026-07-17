<script setup lang="ts">
import type { WatchPartyMessage } from '~/types'

const props = defineProps<{
  messages: readonly WatchPartyMessage[]
  disabled?: boolean
}>()
const emit = defineEmits<{
  send: [message: string]
}>()

const draft = ref('')
const messageList = useTemplateRef<HTMLElement>('messageList')

function send() {
  const message = draft.value.trim()
  if (!message || props.disabled) return
  emit('send', message)
  draft.value = ''
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

watch(() => props.messages.length, async () => {
  await nextTick()
  messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' })
})
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col" aria-labelledby="party-chat-title">
    <div class="mb-3 flex items-center justify-between">
      <h2 id="party-chat-title" class="text-sm font-black text-ink">گفت‌وگوی زنده</h2>
      <span class="inline-flex items-center gap-1.5 text-[10px] font-bold text-muted"><span class="size-1.5 rounded-full bg-crimson" />زنده</span>
    </div>
    <div ref="messageList" class="min-h-52 flex-1 space-y-3 overflow-y-auto rounded-xl border border-line bg-canvas-soft p-3 lg:min-h-0">
      <article v-for="message in messages" :key="message.id" class="group">
        <div class="flex items-baseline justify-between gap-3">
          <p class="truncate text-[11px] font-black text-primary-400">{{ message.user.display_name }}</p>
          <time :datetime="message.created_at" class="font-latin shrink-0 text-[9px] text-disabled">{{ formatTime(message.created_at) }}</time>
        </div>
        <p class="mt-1 whitespace-pre-wrap break-words text-xs leading-6 text-secondary">{{ message.message }}</p>
      </article>
      <div v-if="!messages.length" class="grid h-full min-h-40 place-items-center text-center">
        <div><CinematicIcon name="comments" class="mx-auto size-7 text-muted" /><p class="mt-2 text-xs font-bold text-secondary">گفت‌وگو را شروع کنید</p><p class="mt-1 text-[10px] text-muted">پیام‌ها برای اعضای همین اتاق نمایش داده می‌شوند.</p></div>
      </div>
    </div>
    <form class="mt-3 flex gap-2" @submit.prevent="send">
      <label class="sr-only" for="watch-party-message">پیام</label>
      <input id="watch-party-message" v-model="draft" maxlength="1000" autocomplete="off" :disabled="disabled" placeholder="پیامی بنویسید…" class="min-h-11 min-w-0 flex-1 rounded-xl border border-line bg-elevated px-3 text-xs text-ink outline-none transition placeholder:text-muted focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 disabled:cursor-not-allowed">
      <button type="submit" :disabled="disabled || !draft.trim()" class="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl bg-primary-500 px-4 text-xs font-black text-night-950 transition hover:bg-primary-400 active:bg-primary-600 disabled:bg-disabled">
        <CinematicIcon name="comment" class="size-4" />ارسال
      </button>
    </form>
  </section>
</template>

<script setup lang="ts">
import type { WatchPartyMessage } from '~/types'

const props = defineProps<{
  messages: readonly WatchPartyMessage[]
  disabled?: boolean
  compact?: boolean
}>()
const emit = defineEmits<{
  send: [message: string]
}>()

const draft = ref('')
const messageList = useTemplateRef<HTMLElement>('messageList')
const MAX_LEN = 1000
const instanceId = useId()
const titleId = `party-chat-title-${instanceId}`
const inputId = `party-chat-message-${instanceId}`

function send() {
  const message = draft.value.trim()
  if (!message || props.disabled) return
  emit('send', message)
  draft.value = ''
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function initial(name: string) {
  return name.trim().charAt(0) || '؟'
}

watch(() => props.messages.length, async () => {
  await nextTick()
  messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' })
})
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col" :aria-labelledby="titleId">
    <div class="mb-2 flex items-center justify-between">
      <h3 :id="titleId" class="text-xs font-black text-white/80">گفت‌وگوی زنده</h3>
      <span class="inline-flex items-center gap-1.5 text-[10px] font-bold text-white/35">
        <span class="size-1.5 animate-pulse rounded-full bg-success" />زنده
      </span>
    </div>
    <div
      ref="messageList"
      class="space-y-2.5 overflow-y-auto overscroll-contain rounded-xl border border-white/8 bg-black/35 p-2.5"
      :class="compact
        ? 'min-h-24 flex-1'
        : 'h-[clamp(11rem,38dvh,24rem)] flex-none lg:h-auto lg:min-h-0 lg:flex-1'"
    >
      <article
        v-for="message in messages"
        :key="message.id"
        class="flex gap-2 rounded-xl px-1 py-1 transition hover:bg-white/[.03]"
      >
        <span class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary-500/15 text-[11px] font-black text-primary-300">
          {{ initial(message.user.display_name) }}
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline justify-between gap-2">
            <p class="truncate text-[11px] font-black text-primary-300">{{ message.user.display_name }}</p>
            <time :datetime="message.created_at" class="font-latin shrink-0 text-[9px] text-white/30">{{ formatTime(message.created_at) }}</time>
          </div>
          <p class="mt-0.5 whitespace-pre-wrap break-words text-xs leading-6 text-white/70">{{ message.message }}</p>
        </div>
      </article>
      <div v-if="!messages.length" class="grid h-full min-h-36 place-items-center px-4 text-center">
        <div>
          <span class="mx-auto grid size-12 place-items-center rounded-2xl bg-white/5 ring-1 ring-white/10">
            <CinematicIcon name="comments" class="size-6 text-white/35" />
          </span>
          <p class="mt-3 text-sm font-black text-white/70">هنوز پیامی نیست</p>
          <p class="mt-1.5 text-[11px] leading-5 text-white/40">
            واکنش کوتاه بنویس؛ همه در اتاق آن را می‌بینند.
            <span class="block text-white/30">از اسپویل زیاد پرهیز کن.</span>
          </p>
        </div>
      </div>
    </div>
    <form class="mt-3 flex gap-2" @submit.prevent="send">
      <div class="min-w-0 flex-1">
        <label class="sr-only" :for="inputId">پیام</label>
        <input
          :id="inputId"
          v-model="draft"
          :maxlength="MAX_LEN"
          autocomplete="off"
          :disabled="disabled"
          placeholder="واکنش سریع بنویس…"
          class="min-h-11 w-full rounded-xl border border-white/10 bg-white/[.04] px-3 text-xs text-white outline-none transition placeholder:text-white/30 focus:border-primary-500/50 focus:ring-2 focus:ring-primary-500/15 disabled:cursor-not-allowed"
        >
        <p class="mt-1 px-1 text-left font-latin text-[9px] text-white/30" dir="ltr">
          {{ draft.length }}/{{ MAX_LEN }}
        </p>
      </div>
      <button
        type="submit"
        :disabled="disabled || !draft.trim()"
        class="inline-flex min-h-11 shrink-0 self-start items-center gap-1.5 rounded-xl bg-primary-500 px-4 text-xs font-black text-night-950 transition hover:bg-primary-400 disabled:bg-white/10 disabled:text-white/30"
      >
        <CinematicIcon name="comment" class="size-4" />ارسال
      </button>
    </form>
  </section>
</template>

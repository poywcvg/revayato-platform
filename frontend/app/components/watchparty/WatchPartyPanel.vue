<script setup lang="ts">
import type { WatchPartyConnectionStatus, WatchPartyMember, WatchPartyMessage, WatchRoom } from '~/types'

const props = defineProps<{
  room: WatchRoom
  members: readonly WatchPartyMember[]
  messages: readonly WatchPartyMessage[]
  connectionStatus: WatchPartyConnectionStatus
  inviteUrl: string
  errorMessage?: string
  latencyMs: number | null
}>()
defineEmits<{
  send: [message: string]
  retry: []
  leave: []
  end: []
}>()

const activeTab = ref<'chat' | 'members'>('chat')
const connected = computed(() => props.connectionStatus === 'connected')
const latencyLabel = computed(() => {
  if (props.latencyMs === null) return 'در حال اندازه‌گیری'
  return `${Math.max(0, Math.round(props.latencyMs))}ms`
})
const latencyTone = computed(() => {
  if (props.latencyMs === null) return 'text-muted'
  if (props.latencyMs <= 90) return 'text-success'
  if (props.latencyMs <= 180) return 'text-warning'
  return 'text-error'
})
const statusLabel = computed(() => ({
  idle: 'آماده',
  connecting: 'در حال وصل شدن…',
  connected: 'متصل',
  reconnecting: 'وصل شدن دوباره…',
  disconnected: 'قطع شده',
  error: 'وصل نشد',
})[props.connectionStatus])
</script>

<template>
  <aside class="flex min-h-[520px] flex-col rounded-2xl border border-line bg-surface p-3.5 shadow-2xl shadow-black/25 sm:p-4 lg:h-[min(78vh,760px)]" aria-label="پنل تماشای گروهی">
    <div class="mb-3 flex items-center justify-between gap-3 border-b border-line pb-3">
      <div class="min-w-0">
        <p class="text-[10px] font-black uppercase tracking-[0.18em] text-crimson-hover">Watch Party</p>
        <h1 class="mt-1 truncate text-sm font-black text-ink">{{ room.content.title }}</h1>
      </div>
      <span class="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-elevated px-2 py-1 text-[10px] font-bold" :class="connected ? 'text-success' : 'text-warning'">
        <span class="size-1.5 rounded-full" :class="connected ? 'bg-success' : 'bg-warning'" />{{ statusLabel }}
      </span>
    </div>

    <div class="mb-3 flex items-center justify-between rounded-xl border border-line bg-canvas-soft px-3 py-2 text-[10px]">
      <span class="inline-flex items-center gap-1.5 text-muted"><CinematicIcon name="bolt" class="size-3.5" />همگام‌سازی هوشمند</span>
      <span class="font-black" :class="latencyTone">تاخیر {{ latencyLabel }}</span>
    </div>

    <WatchPartyInvite :invite-code="room.invite_code" :invite-url="inviteUrl" />

    <div v-if="connectionStatus === 'reconnecting' || connectionStatus === 'error'" class="mt-3 flex items-center justify-between gap-3 rounded-xl border border-warning/20 bg-warning/10 p-2.5 text-[11px] text-secondary">
      <span>{{ errorMessage || 'ارتباط اتاق موقتاً قطع شده است.' }}</span>
      <button type="button" class="min-h-10 shrink-0 rounded-lg bg-elevated px-2.5 py-1.5 font-black text-ink ring-1 ring-line hover:bg-primary-500/15 hover:text-primary-400" @click="$emit('retry')">تلاش دوباره</button>
    </div>

    <div class="my-3 grid grid-cols-2 rounded-xl bg-canvas-soft p-1 ring-1 ring-line">
      <button type="button" class="min-h-9 rounded-lg text-xs font-black transition" :class="activeTab === 'chat' ? 'bg-elevated text-primary-400 shadow-sm' : 'text-muted hover:text-ink'" @click="activeTab = 'chat'">گفت‌وگو</button>
      <button type="button" class="min-h-9 rounded-lg text-xs font-black transition" :class="activeTab === 'members' ? 'bg-elevated text-primary-400 shadow-sm' : 'text-muted hover:text-ink'" @click="activeTab = 'members'">اعضا · {{ members.length }}</button>
    </div>

    <WatchPartyChat v-if="activeTab === 'chat'" :messages="messages" :disabled="!connected || room.status !== 'active'" @send="$emit('send', $event)" />
    <div v-else class="min-h-0 flex-1 overflow-y-auto"><WatchPartyMembers :members="members" /></div>

    <div class="mt-3 border-t border-line pt-3">
      <button v-if="room.is_host" type="button" class="min-h-10 w-full rounded-xl border border-error/25 bg-error/10 text-xs font-black text-error transition hover:border-error/40 hover:bg-error/15" @click="$emit('end')">پایان تماشای گروهی</button>
      <button v-else type="button" class="min-h-10 w-full rounded-xl border border-line bg-elevated text-xs font-black text-secondary transition hover:border-primary-500/35 hover:bg-primary-500/10 hover:text-primary-400" @click="$emit('leave')">خروج از اتاق</button>
    </div>
  </aside>
</template>

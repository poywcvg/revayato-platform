<script setup lang="ts">
import type { WatchPartyConnectionStatus, WatchPartyMember, WatchPartyMessage, WatchRoom } from '~/types'

const props = withDefaults(defineProps<{
  room: WatchRoom
  members: readonly WatchPartyMember[]
  messages: readonly WatchPartyMessage[]
  connectionStatus: WatchPartyConnectionStatus
  inviteUrl: string
  errorMessage?: string
  latencyMs: number | null
  actionPending?: boolean
}>(), {
  errorMessage: '',
  actionPending: false,
})
const emit = defineEmits<{
  send: [message: string]
  retry: []
  leave: []
  end: []
  close: []
}>()

const activeTab = defineModel<'chat' | 'members' | 'invite'>('activeTab', { default: 'chat' })
const confirmingEnd = ref(false)

const connected = computed(() => props.connectionStatus === 'connected')
const latencyLabel = computed(() => {
  if (props.latencyMs === null) return '…'
  return `${Math.max(0, Math.round(props.latencyMs))}ms`
})
const latencyTone = computed(() => {
  if (props.latencyMs === null) return 'text-white/40'
  if (props.latencyMs <= 90) return 'text-success'
  if (props.latencyMs <= 180) return 'text-warning'
  return 'text-error'
})
const statusLabel = computed(() => ({
  idle: 'آماده',
  connecting: 'وصل شدن…',
  connected: 'متصل',
  reconnecting: 'وصل دوباره…',
  disconnected: 'قطع',
  error: 'خطا',
})[props.connectionStatus])
const statusTone = computed(() => {
  if (props.connectionStatus === 'connected') return 'text-success'
  if (props.connectionStatus === 'error' || props.connectionStatus === 'disconnected') return 'text-error'
  return 'text-warning'
})
const statusDotTone = computed(() => {
  if (props.connectionStatus === 'connected') return 'bg-success'
  if (props.connectionStatus === 'error' || props.connectionStatus === 'disconnected') return 'bg-error'
  return 'bg-warning'
})
const onlineCount = computed(() => props.members.filter(member => member.is_online).length)

const tabs = [
  { id: 'chat' as const, label: 'گفت‌وگو', icon: 'comments' as const },
  { id: 'members' as const, label: 'اعضا', icon: 'users' as const },
  { id: 'invite' as const, label: 'دعوت', icon: 'user-plus' as const },
]

function chooseTab(tab: 'chat' | 'members' | 'invite') {
  activeTab.value = tab
  confirmingEnd.value = false
}

function requestEnd() {
  if (!confirmingEnd.value) {
    confirmingEnd.value = true
    return
  }
  confirmingEnd.value = false
  emit('end')
}
</script>

<template>
  <aside
    class="watch-party-panel flex max-h-[78dvh] flex-col bg-[#0c0c0c]/95 p-3.5 shadow-2xl shadow-black/50 backdrop-blur-xl sm:p-4 lg:h-[min(78vh,760px)] lg:max-h-none"
    aria-label="پنل تماشای گروهی"
  >
    <div class="mb-2 flex justify-center lg:hidden" aria-hidden="true">
      <span class="h-1 w-10 rounded-full bg-white/25" />
    </div>

    <div class="mb-3 flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="text-[10px] font-black uppercase tracking-[0.16em] text-crimson-hover">Watch Party</p>
        <h2 class="mt-1 truncate text-sm font-black text-white">اتاق خصوصی</h2>
        <p class="mt-0.5 text-[10px] text-white/40">
          {{ onlineCount.toLocaleString('fa-IR') }} آنلاین · تاخیر
          <span class="font-latin" :class="latencyTone">{{ latencyLabel }}</span>
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span
          class="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-white/5 px-2 py-1 text-[10px] font-bold"
          :class="statusTone"
        >
          <span class="size-1.5 rounded-full" :class="statusDotTone" />{{ statusLabel }}
        </span>
        <button
          type="button"
          class="grid size-11 place-items-center rounded-lg bg-white/5 text-white/50 hover:bg-white/10 hover:text-white lg:hidden"
          aria-label="بستن"
          @click="$emit('close')"
        >
          <CinematicIcon name="chevron-down" class="size-4" />
        </button>
      </div>
    </div>

    <div v-if="connectionStatus === 'reconnecting' || connectionStatus === 'error'" class="mb-3 flex items-center justify-between gap-3 rounded-xl border border-warning/25 bg-warning/10 p-2.5 text-[11px] text-white/75">
      <span>{{ errorMessage || 'ارتباط اتاق موقتاً قطع شده است.' }}</span>
      <button type="button" class="min-h-11 shrink-0 rounded-lg bg-warning px-3 py-1.5 font-black text-[#201500] transition hover:brightness-110" @click="$emit('retry')">تلاش دوباره</button>
    </div>

    <div class="mb-3 grid grid-cols-3 rounded-xl bg-white/[.04] p-1 ring-1 ring-white/8" role="tablist" aria-label="بخش‌های اتاق">
      <button
        v-for="tab in tabs"
        :id="`party-tab-${tab.id}`"
        :key="tab.id"
        type="button"
        role="tab"
        class="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-lg text-[11px] font-black transition"
        :class="activeTab === tab.id
          ? tab.id === 'invite'
            ? 'bg-info/15 text-info ring-1 ring-info/15'
            : tab.id === 'members'
              ? 'bg-success/12 text-success ring-1 ring-success/15'
              : 'bg-primary-500/15 text-primary-300 ring-1 ring-primary-500/15'
          : 'text-white/45 hover:bg-white/5 hover:text-white'"
        :aria-selected="activeTab === tab.id"
        :aria-controls="`party-panel-${tab.id}`"
        @click="chooseTab(tab.id)"
      >
        <CinematicIcon :name="tab.icon" class="size-3.5" />
        {{ tab.label }}
        <span v-if="tab.id === 'members'" class="font-latin text-[9px] opacity-70">{{ onlineCount }}</span>
      </button>
    </div>

    <WatchPartyChat v-if="activeTab === 'chat'" id="party-panel-chat" role="tabpanel" aria-labelledby="party-tab-chat" :messages="messages" :disabled="!connected || room.status !== 'active'" @send="$emit('send', $event)" />
    <div v-else-if="activeTab === 'members'" id="party-panel-members" role="tabpanel" aria-labelledby="party-tab-members" class="min-h-0 flex-1 overflow-y-auto">
      <WatchPartyMembers :members="members" />
    </div>
    <div v-else id="party-panel-invite" role="tabpanel" aria-labelledby="party-tab-invite" class="min-h-0 flex-1 overflow-y-auto">
      <WatchPartyInvite :invite-code="room.invite_code" :invite-url="inviteUrl" />
    </div>

    <div class="mt-3 border-t border-white/8 pt-3">
      <div v-if="room.is_host && confirmingEnd" class="grid grid-cols-2 gap-2 rounded-xl border border-error/20 bg-error/8 p-2">
        <button
          type="button"
          class="party-panel-btn party-panel-btn--ghost"
          :disabled="actionPending"
          @click="confirmingEnd = false"
        >
          انصراف
        </button>
        <button
          type="button"
          class="party-panel-btn party-panel-btn--danger-solid"
          :disabled="actionPending"
          @click="requestEnd"
        >
          {{ actionPending ? '…' : 'پایان' }}
        </button>
      </div>
      <button
        v-else-if="room.is_host"
        type="button"
        class="party-panel-btn party-panel-btn--danger"
        :disabled="actionPending"
        @click="requestEnd"
      >
        <CinematicIcon name="trash" class="size-3.5" />
        پایان اتاق
      </button>
      <button
        v-else
        type="button"
        class="party-panel-btn party-panel-btn--leave"
        :disabled="actionPending"
        @click="$emit('leave')"
      >
        <CinematicIcon name="logout" class="size-3.5" />
        {{ actionPending ? '…' : 'خروج' }}
      </button>
    </div>
  </aside>
</template>

<style scoped>
.watch-party-panel {
  padding-bottom: max(0.875rem, env(safe-area-inset-bottom, 0px));
}

.party-panel-btn {
  display: inline-flex;
  min-height: 2.75rem;
  width: 100%;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  border-radius: 0.85rem;
  border: 1px solid transparent;
  padding-inline: 0.75rem;
  font-size: 0.75rem;
  font-weight: 900;
  transition:
    transform 160ms ease,
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 180ms ease,
    filter 160ms ease;
}

.party-panel-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.party-panel-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.party-panel-btn:disabled {
  opacity: 0.5;
}

.party-panel-btn--ghost {
  color: rgb(255 255 255 / 70%);
  background: rgb(255 255 255 / 7%);
}

.party-panel-btn--ghost:hover:not(:disabled) {
  color: #fff;
  background: rgb(255 255 255 / 12%);
}

.party-panel-btn--danger {
  color: #fca5a5;
  background: rgb(239 68 68 / 12%);
  border-color: rgb(248 113 113 / 28%);
}

.party-panel-btn--danger:hover:not(:disabled) {
  color: #fff1f2;
  background: rgb(239 68 68 / 22%);
  border-color: rgb(248 113 113 / 48%);
  box-shadow: 0 8px 20px rgb(239 68 68 / 18%);
}

.party-panel-btn--danger-solid {
  color: #2a0707;
  background: #ef4444;
}

.party-panel-btn--danger-solid:hover:not(:disabled) {
  filter: brightness(1.08);
  box-shadow: 0 8px 20px rgb(239 68 68 / 28%);
}

.party-panel-btn--leave {
  color: #fbbf24;
  background: rgb(245 158 11 / 10%);
  border-color: rgb(251 191 36 / 24%);
}

.party-panel-btn--leave:hover:not(:disabled) {
  color: #fff7ed;
  background: rgb(245 158 11 / 20%);
  border-color: rgb(251 191 36 / 42%);
  box-shadow: 0 8px 20px rgb(245 158 11 / 16%);
}

@media (orientation: landscape) and (max-height: 500px) and (max-width: 1023px) {
  .watch-party-panel {
    height: 100dvh;
    max-height: 100dvh;
    padding-top: max(0.625rem, env(safe-area-inset-top, 0px));
  }
}
</style>

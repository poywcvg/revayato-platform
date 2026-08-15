<script setup lang="ts">
import type { WatchPartyMember, WatchPartyPlaybackState } from '~/types'

const props = defineProps<{
  members: readonly WatchPartyMember[]
  playbackState?: WatchPartyPlaybackState | null
  isHost?: boolean
  latencyMs?: number | null
}>()

const onlineMembers = computed(() => props.members.filter(member => member.is_online))
const host = computed(() => props.members.find(member => member.role === 'host'))
const playing = computed(() => Boolean(props.playbackState?.is_playing))

function initial(name: string) {
  return name.trim().charAt(0) || '؟'
}

function formatTime(seconds?: number) {
  const total = Math.max(0, Math.floor(seconds || 0))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

const syncLabel = computed(() => {
  if (!props.playbackState) return 'در انتظار همگام‌سازی'
  return playing.value ? 'پخش هم‌زمان' : 'متوقف · همگام'
})
</script>

<template>
  <div class="party-presence flex flex-wrap items-center justify-between gap-2.5">
    <div class="flex min-w-0 items-center gap-2.5">
      <div class="flex -space-x-2 space-x-reverse" aria-label="اعضای آنلاین">
        <div
          v-for="member in onlineMembers.slice(0, 5)"
          :key="member.user.id"
          class="relative"
          :title="member.user.display_name"
        >
          <img
            v-if="member.user.avatar"
            :src="member.user.avatar"
            :alt="member.user.display_name"
            class="size-7 rounded-full object-cover ring-2 ring-black/80"
          >
          <span
            v-else
            class="grid size-7 place-items-center rounded-full bg-primary-500/20 text-[10px] font-black text-primary-300 ring-2 ring-black/80"
          >{{ initial(member.user.display_name) }}</span>
          <span
            v-if="member.role === 'host'"
            class="absolute -bottom-0.5 -left-0.5 size-2 rounded-full bg-primary-500 ring-2 ring-black/80"
          />
        </div>
        <span
          v-if="onlineMembers.length > 5"
          class="grid size-7 place-items-center rounded-full bg-white/10 text-[9px] font-black text-white/80 ring-2 ring-black/80"
        >+{{ onlineMembers.length - 5 }}</span>
      </div>
      <div class="min-w-0">
        <p class="truncate text-[11px] font-black text-white/90">
          {{ onlineMembers.length.toLocaleString('fa-IR') }} آنلاین
          <span v-if="host" class="text-white/40"> · {{ host.user.display_name }}</span>
        </p>
        <p class="mt-0.5 flex items-center gap-1.5 text-[10px] font-bold" :class="playing ? 'text-primary-300' : 'text-white/45'">
          <span class="size-1.5 rounded-full" :class="playing ? 'animate-pulse bg-primary-400' : 'bg-white/35'" />
          {{ syncLabel }}
          <span v-if="playbackState" class="font-latin text-white/30">{{ formatTime(playbackState.position_seconds) }}</span>
        </p>
      </div>
    </div>
    <div class="flex items-center gap-1.5 text-[10px] font-bold">
      <span
        v-if="isHost"
        class="rounded-md bg-primary-500/20 px-2 py-1 text-primary-300"
      >میزبان · کنترل با شما</span>
      <span
        v-else
        class="rounded-md bg-white/8 px-2 py-1 text-white/50"
      >مهمان · فقط میزبان</span>
      <span v-if="latencyMs != null" class="font-latin hidden text-white/35 sm:inline">{{ Math.round(latencyMs) }}ms</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { WatchPartyMember } from '~/types'

defineProps<{
  members: readonly WatchPartyMember[]
}>()

function initial(name: string) {
  return name.trim().charAt(0) || '؟'
}
</script>

<template>
  <section aria-labelledby="party-members-title">
    <div class="mb-3 flex items-center justify-between">
      <h2 id="party-members-title" class="text-sm font-black text-ink">اعضای اتاق</h2>
      <span class="rounded-full bg-elevated px-2 py-0.5 text-[10px] font-bold text-secondary">{{ members.length }} نفر</span>
    </div>
    <ul v-if="members.length" class="space-y-2">
      <li v-for="member in members" :key="member.user.id" class="flex items-center gap-3 rounded-xl border border-transparent bg-canvas-soft p-2.5 transition hover:border-line hover:bg-elevated">
        <div class="relative shrink-0">
          <img v-if="member.user.avatar" :src="member.user.avatar" :alt="member.user.display_name" class="size-9 rounded-full object-cover ring-1 ring-line">
          <span v-else class="grid size-9 place-items-center rounded-full bg-primary-500/15 text-sm font-black text-primary-400 ring-1 ring-primary-500/25">{{ initial(member.user.display_name) }}</span>
          <span class="absolute -bottom-0.5 -left-0.5 size-2.5 rounded-full border-2 border-canvas-soft" :class="member.is_online ? 'bg-success' : 'bg-disabled'" :title="member.is_online ? 'آنلاین' : 'آفلاین'" />
        </div>
        <div class="min-w-0 flex-1">
          <p class="truncate text-xs font-bold text-ink">{{ member.user.display_name }}</p>
          <p class="mt-0.5 text-[10px] text-muted">{{ member.is_online ? 'در اتاق' : 'آفلاین' }}</p>
        </div>
        <span v-if="member.role === 'host'" class="rounded-lg bg-primary-500/15 px-2 py-1 text-[10px] font-black text-primary-400 ring-1 ring-primary-500/25">میزبان</span>
      </li>
    </ul>
    <div v-else class="grid min-h-32 place-items-center rounded-xl border border-dashed border-line bg-canvas-soft p-5 text-center">
      <div><CinematicIcon name="users" class="mx-auto size-6 text-muted" /><p class="mt-2 text-xs text-muted">هنوز عضوی در اتاق نیست.</p></div>
    </div>
  </section>
</template>

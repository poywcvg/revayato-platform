<script setup lang="ts">
withDefaults(defineProps<{ isDubbed?: boolean; hasSubtitle?: boolean; compact?: boolean; dark?: boolean }>(), {
  isDubbed: false,
  hasSubtitle: false,
  compact: false,
  dark: false,
})
</script>

<template>
  <span v-if="isDubbed || hasSubtitle" class="inline-flex flex-wrap items-center gap-1.5">
    <span v-if="isDubbed" class="inline-flex items-center gap-1 rounded-lg bg-primary-500/14 px-2 py-1 text-[10px] font-black text-primary-300 ring-1 ring-inset ring-primary-400/25"><CinematicIcon name="audio" class="size-3.5" />{{ compact ? 'دوبله' : 'دوبله فارسی' }}</span>
    <span v-if="hasSubtitle" class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-black ring-1 ring-inset" :class="dark ? 'bg-white/5 text-secondary ring-white/10' : 'bg-elevated text-secondary ring-line'"><CinematicIcon name="subtitle" class="size-3.5" />{{ compact ? 'زیرنویس' : 'زیرنویس فارسی' }}</span>
  </span>
</template>

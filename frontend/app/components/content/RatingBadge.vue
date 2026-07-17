<script setup lang="ts">
defineProps<{ rating: number; compact?: boolean }>()
</script>

<template>
  <span class="inline-flex items-center gap-1 rounded-lg bg-elevated/95 px-2 py-1 text-xs font-black text-ink shadow-sm ring-1 ring-line">
    <CinematicIcon name="star" class="size-4 text-primary-500" filled />
    {{ rating.toFixed(1) }}<span v-if="!compact" class="font-medium text-slate-400">/ ۱۰</span>
  </span>
</template>

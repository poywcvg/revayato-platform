<script setup lang="ts">
withDefaults(defineProps<{ count?: number }>(), { count: 6 })
</script>

<template>
  <div class="grid grid-cols-2 gap-3.5 sm:grid-cols-3 sm:gap-5 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6" aria-label="در حال بارگذاری">
    <div v-for="index in count" :key="index" class="animate-pulse overflow-hidden rounded-2xl bg-surface ring-1 ring-line">
      <div class="aspect-[2/3] bg-elevated" />
      <div class="space-y-2 p-3.5"><div class="h-4 w-3/4 rounded bg-elevated" /><div class="h-3 w-1/2 rounded bg-line" /></div>
    </div>
  </div>
</template>

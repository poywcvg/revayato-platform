<script setup lang="ts">
withDefaults(defineProps<{ count?: number }>(), { count: 6 })
</script>

<template>
  <div class="catalog-grid" aria-label="در حال بارگذاری" aria-busy="true" role="status">
    <span class="sr-only">در حال بارگذاری فهرست محتوا</span>
    <div v-for="index in count" :key="index" class="cinematic-card skeleton-card overflow-hidden rounded-[1.35rem]">
      <div class="aspect-[2/3] bg-elevated" />
      <div class="space-y-2.5 p-3.5"><div class="h-4 w-3/4 rounded-lg bg-elevated" /><div class="h-3 w-1/2 rounded-lg bg-line" /></div>
    </div>
  </div>
</template>

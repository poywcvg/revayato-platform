<script setup lang="ts">
defineProps<{ title: string; eyebrow: string; description: string; items: Array<{ title: string; text: string }> }>()
</script>

<template>
  <div class="pb-12">
    <div class="page-shell pt-8 sm:pt-11"><PageHero :title="title" :eyebrow="eyebrow" :description="description" icon="document" /></div>
    <main class="page-shell grid gap-4 sm:grid-cols-2"><section v-for="(item, index) in items" :key="item.title" class="info-card ui-surface render-later group relative overflow-hidden p-5 sm:p-6"><div class="flex items-center justify-between gap-4"><span class="grid size-10 place-items-center rounded-xl bg-primary-500/14 text-xs font-black text-primary-300 ring-1 ring-primary-500/20 tabular-nums">{{ String(index + 1).padStart(2, '0') }}</span><span class="h-px flex-1 bg-gradient-to-l from-primary-500/35 to-transparent" aria-hidden="true" /></div><h2 class="mt-4 text-lg font-black text-ink">{{ item.title }}</h2><p class="mt-2 text-sm leading-7 text-secondary">{{ item.text }}</p></section></main>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  showWordmark?: boolean
  compactOnMobile?: boolean
}>(), {
  showWordmark: true,
  compactOnMobile: true,
})
</script>

<template>
  <NuxtLink to="/" class="group inline-flex min-h-11 shrink-0 items-center gap-2.5 text-white" aria-label="روایتو، خانه" aria-current-value="false">
    <span class="cinema-glow relative grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-[15px] bg-gradient-to-br from-primary-500/18 via-white/[.06] to-crimson/12 text-primary-300 ring-1 ring-primary-300/25 transition group-hover:-rotate-2 group-hover:ring-primary-300/45">
      <span class="ambient-orb absolute -bottom-2 -left-2 h-6 w-6 rounded-full" />
      <svg class="relative size-7" viewBox="0 0 40 40" fill="none" aria-hidden="true">
        <path d="M7.5 11.5c4.2-2.4 8.8-2.4 12.5.25v17c-3.7-2.65-8.3-2.65-12.5-.25v-17Z" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M32.5 11.5c-4.2-2.4-8.8-2.4-12.5.25v17c3.7-2.65 8.3-2.65 12.5-.25v-17Z" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" opacity=".72" />
        <path d="m17.1 15.7 8.6 5.45-8.6 5.45V15.7Z" fill="var(--color-primary-400)" stroke="var(--color-night-950)" stroke-width="1.2" stroke-linejoin="round" />
      </svg>
    </span>
    <span v-if="showWordmark" :class="compactOnMobile ? 'hidden xl:block' : 'block'">
      <span class="block whitespace-nowrap text-base font-black leading-none">روایتو</span>
      <span class="mt-1 block font-latin text-[9px] font-bold tracking-[.12em] text-primary-400">REVAYATO</span>
    </span>
  </NuxtLink>
</template>

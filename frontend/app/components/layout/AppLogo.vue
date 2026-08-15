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
  <NuxtLink to="/" class="group inline-flex min-h-11 shrink-0 items-center gap-1.5 text-ink lg:gap-2.5" aria-label="روایتو، خانه" aria-current-value="false">
    <span class="relative grid size-9 shrink-0 place-items-center overflow-hidden lg:size-10">
      <img
        src="/assets/brand/logo.svg"
        alt=""
        width="40"
        height="40"
        class="size-full object-contain transition group-hover:scale-[1.04]"
        decoding="async"
      >
    </span>
    <!-- Keep wordmark off phones/tablets so the action icons never collide. -->
    <span v-if="showWordmark" :class="compactOnMobile ? 'hidden lg:block' : 'block'">
      <span class="block whitespace-nowrap text-[15px] font-medium leading-none tracking-tight lg:text-base">روایتو</span>
      <span class="mt-1 block font-latin text-[9px] font-medium tracking-[.14em] text-primary-400">REVAYATO</span>
    </span>
  </NuxtLink>
</template>

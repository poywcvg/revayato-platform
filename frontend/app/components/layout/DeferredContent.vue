<script setup lang="ts">
/**
 * Layout wrapper for home rails. Real content always renders so SSR/hydration
 * stay aligned; pair with Lazy* + hydrate-on-visible for deferred hydration cost.
 */
withDefaults(defineProps<{
  minHeight?: string
  rootMargin?: string
}>(), {
  minHeight: '32rem',
  rootMargin: '220px 0px',
})
</script>

<template>
  <div>
    <slot />
  </div>
</template>

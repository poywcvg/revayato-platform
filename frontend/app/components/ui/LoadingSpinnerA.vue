<script setup lang="ts">
const props = withDefaults(defineProps<{
  size?: 'small' | 'medium' | 'large'
  spinner1Border?: 'none' | 'thin' | 'medium' | 'thick'
  spinner2Border?: 'none' | 'thin' | 'medium' | 'thick'
  alignContent?: 'vertical' | 'center'
  variant?: 'default' | 'blue' | 'red'
  label?: string
}>(), {
  size: 'medium',
  spinner1Border: 'thin',
  spinner2Border: 'thick',
  alignContent: 'vertical',
  variant: 'default',
  label: 'در حال بارگذاری',
})

// spinner1Border / spinner2Border kept for API compatibility with existing
// call sites; the blade spinner has no ring borders so they are inert.
const wrapperClasses = computed(() => [
  `loading-spinner-a--${props.size}`,
  `loading-spinner-a--${props.alignContent}`,
  `loading-spinner-a--${props.variant}`,
])

// 10 radial blades, evenly spaced, animated with a staggered ripple.
const blades = Array.from({ length: 10 }, (_, i) => ({
  rotation: (i + 1) * 36,
  delay: (i + 1) / 10,
}))
</script>

<template>
  <div class="loading-spinner-a" :class="wrapperClasses" role="status" aria-live="polite">
    <span class="loading-spinner-a__spinners" aria-hidden="true">
      <span class="loading-spinner-a__blades">
        <span
          v-for="b in blades"
          :key="b.rotation"
          class="loading-spinner-a__blade"
          :style="{ '--rotation': b.rotation, '--delay': b.delay }"
        />
      </span>
    </span>
    <span v-if="$slots.default" class="loading-spinner-a__content"><slot /></span>
    <span v-else class="sr-only">{{ label }}</span>
  </div>
</template>

<style scoped>
.loading-spinner-a {
  --spinner-color: var(--theme-accent-primary);
  display: inline-flex;
  color: var(--theme-text-secondary);
}
/* The blade ring visually extends ~3x the base unit outward from centre, so
   reserve a square footprint and place the tiny base cell at its centre. */
.loading-spinner-a__spinners {
  position: relative;
  display: inline-grid;
  width: var(--spinner-size);
  height: var(--spinner-size);
  flex: none;
  place-items: center;
}
.loading-spinner-a__blades {
  position: relative;
  width: calc(var(--spinner-size) / 6);
  height: calc(var(--spinner-size) / 6);
}
.loading-spinner-a__blade {
  position: absolute;
  top: 0;
  left: 0;
  width: 50%;
  height: 150%;
  border-radius: 999px;
  background: var(--spinner-color);
  transform: rotate(calc(var(--rotation) * 1deg)) translate(0, 150%);
  animation: spinner-a-ripple 1s calc(var(--delay) * 1s) infinite ease;
}
@keyframes spinner-a-ripple {
  0%, 10%, 20%, 30%, 50%, 60%, 70%, 80%, 90%, 100% {
    transform: rotate(calc(var(--rotation) * 1deg)) translate(0, 150%);
  }
  50% {
    transform: rotate(calc(var(--rotation) * 1deg)) translate(0, 225%);
  }
}
.loading-spinner-a--small { --spinner-size: 1rem; font-size: .72rem; }
.loading-spinner-a--medium { --spinner-size: 2rem; font-size: .82rem; }
.loading-spinner-a--large { --spinner-size: 3.25rem; font-size: .9rem; }
.loading-spinner-a--vertical { flex-direction: column; align-items: center; gap: .75rem; text-align: center; }
.loading-spinner-a--center { align-items: center; gap: .65rem; }
.loading-spinner-a--blue { --spinner-color: var(--theme-info); }
.loading-spinner-a--red { --spinner-color: var(--theme-accent-crimson); }
.loading-spinner-a__content { font-weight: 700; line-height: 1.8; }
@media (prefers-reduced-motion: reduce) {
  .loading-spinner-a__blade { animation-duration: 2.2s; }
}
</style>

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

const wrapperClasses = computed(() => [
  `loading-spinner-a--${props.size}`,
  `loading-spinner-a--${props.alignContent}`,
  `loading-spinner-a--s1-${props.spinner1Border}`,
  `loading-spinner-a--s2-${props.spinner2Border}`,
  `loading-spinner-a--${props.variant}`,
])
</script>

<template>
  <div class="loading-spinner-a" :class="wrapperClasses" role="status" aria-live="polite">
    <span class="loading-spinner-a__spinners" aria-hidden="true">
      <span class="loading-spinner-a__spinner loading-spinner-a__spinner--1" />
      <span class="loading-spinner-a__spinner loading-spinner-a__spinner--2" />
    </span>
    <span v-if="$slots.default" class="loading-spinner-a__content"><slot /></span>
    <span v-else class="sr-only">{{ label }}</span>
  </div>
</template>

<style scoped>
.loading-spinner-a {
  --spinner-color: var(--theme-accent-primary);
  --spinner-track: color-mix(in srgb, var(--theme-text-primary) 14%, transparent);
  display: inline-flex;
  color: var(--theme-text-secondary);
}
.loading-spinner-a__spinners { position: relative; display: inline-grid; width: var(--spinner-size); height: var(--spinner-size); flex: none; place-items: center; }
.loading-spinner-a__spinner { position: absolute; border-style: solid; border-color: var(--spinner-track); border-radius: 999px; animation: spinner-a-rotate 1.05s linear infinite; }
.loading-spinner-a__spinner--1 { inset: 0; border-top-color: var(--spinner-color); }
.loading-spinner-a__spinner--2 { inset: 24%; border-right-color: var(--spinner-color); animation-direction: reverse; animation-duration: .72s; }
.loading-spinner-a--small { --spinner-size: 1rem; font-size: .72rem; }
.loading-spinner-a--medium { --spinner-size: 2rem; font-size: .82rem; }
.loading-spinner-a--large { --spinner-size: 3.25rem; font-size: .9rem; }
.loading-spinner-a--vertical { flex-direction: column; align-items: center; gap: .75rem; text-align: center; }
.loading-spinner-a--center { align-items: center; gap: .65rem; }
.loading-spinner-a--blue { --spinner-color: var(--theme-info); }
.loading-spinner-a--red { --spinner-color: var(--theme-accent-crimson); }
.loading-spinner-a--s1-none .loading-spinner-a__spinner--1, .loading-spinner-a--s2-none .loading-spinner-a__spinner--2 { border-width: 0; }
.loading-spinner-a--s1-thin .loading-spinner-a__spinner--1, .loading-spinner-a--s2-thin .loading-spinner-a__spinner--2 { border-width: 1px; }
.loading-spinner-a--s1-medium .loading-spinner-a__spinner--1, .loading-spinner-a--s2-medium .loading-spinner-a__spinner--2 { border-width: 2px; }
.loading-spinner-a--s1-thick .loading-spinner-a__spinner--1, .loading-spinner-a--s2-thick .loading-spinner-a__spinner--2 { border-width: 3px; }
.loading-spinner-a__content { font-weight: 700; line-height: 1.8; }
@keyframes spinner-a-rotate { to { transform: rotate(1turn); } }
@media (prefers-reduced-motion: reduce) { .loading-spinner-a__spinner { animation-duration: 2.2s; } }
</style>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  code: string
  title?: string
  size?: 'sm' | 'md' | 'lg'
}>(), {
  title: '',
  size: 'md',
})

const normalized = computed(() => props.code.trim().toUpperCase())
const canRenderFlag = computed(() => /^[A-Z]{2}$/.test(normalized.value) && normalized.value !== 'SU')
const flagSrc = computed(() => `https://flagcdn.com/${normalized.value.toLowerCase()}.svg`)
const failed = ref(false)

watch(normalized, () => { failed.value = false })

const sizeClass = computed(() => ({
  sm: 'country-flag--sm',
  md: 'country-flag--md',
  lg: 'country-flag--lg',
}[props.size]))
</script>

<template>
  <span
    class="country-flag"
    :class="sizeClass"
    :title="title || normalized"
    role="img"
    :aria-label="title || `پرچم ${normalized}`"
  >
    <img
      v-if="canRenderFlag && !failed"
      :src="flagSrc"
      alt=""
      width="40"
      height="28"
      loading="lazy"
      decoding="async"
      referrerpolicy="no-referrer"
      class="country-flag__img"
      @error="failed = true"
    >
    <svg
      v-else
      class="country-flag__fallback"
      viewBox="0 0 40 28"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect width="40" height="28" rx="3" fill="currentColor" opacity="0.1" />
      <rect x="1" y="1" width="38" height="26" rx="2.5" fill="none" stroke="currentColor" stroke-opacity="0.28" stroke-width="1" />
      <path
        d="M12 8.5c3.2 0 5.2 2.1 8 2.1s4.8-2.1 8-2.1M12 14c3.2 0 5.2 2.1 8 2.1s4.8-2.1 8-2.1M12 19.5c3.2 0 5.2 2.1 8 2.1s4.8-2.1 8-2.1"
        fill="none"
        stroke="currentColor"
        stroke-opacity="0.28"
        stroke-width="1.2"
        stroke-linecap="round"
      />
      <text
        x="20"
        y="15.2"
        text-anchor="middle"
        dominant-baseline="middle"
        fill="currentColor"
        font-family="Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
        font-size="9"
        font-weight="700"
        letter-spacing="0.08em"
      >{{ normalized.slice(0, 2) || '?' }}</text>
    </svg>
  </span>
</template>

<style scoped>
.country-flag {
  display: inline-grid;
  place-items: center;
  flex: none;
  overflow: hidden;
  border-radius: 0.4rem;
  color: var(--theme-text-secondary);
  background: color-mix(in srgb, var(--theme-bg-elevated) 80%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-border) 85%, transparent);
}

.country-flag--sm {
  width: 1.75rem;
  height: 1.25rem;
}

.country-flag--md {
  width: 2.5rem;
  height: 1.75rem;
}

.country-flag--lg {
  width: 3.25rem;
  height: 2.25rem;
}

.country-flag__img,
.country-flag__fallback {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>

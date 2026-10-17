<script setup lang="ts">
import type { ThemePreference } from '~/composables/useTheme'

// Follow the device, always light, always dark. «خودکار» is the default.
const { preference, setPreference } = useTheme()
const options: { value: ThemePreference, label: string }[] = [
  { value: 'system', label: 'خودکار' },
  { value: 'light', label: 'روشن' },
  { value: 'dark', label: 'تاریک' },
]
const mounted = ref(false)
onMounted(() => { mounted.value = true })
</script>

<template>
  <div class="theme-mode" role="radiogroup" aria-label="حالت نمایش">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="radio"
      class="theme-mode__option"
      :class="mounted && preference === option.value && 'is-selected'"
      :aria-checked="mounted && preference === option.value"
      @click="setPreference(option.value)"
    >
      {{ option.label }}
    </button>
  </div>
  <p class="theme-mode__hint">«خودکار» مثل تنظیم گوشی یا سیستم روشن یا تاریک می‌شود.</p>
</template>

<style scoped>
.theme-mode {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 3px;
  border-radius: .8rem;
  background: color-mix(in srgb, var(--theme-text-primary) 6%, transparent);
  padding: 3px;
}

.theme-mode__option {
  min-height: 2.35rem;
  border-radius: .6rem;
  color: var(--theme-text-secondary);
  font-size: .8rem;
  font-weight: 700;
  transition: background-color .15s ease, color .15s ease;
}

.theme-mode__option:hover { color: var(--theme-text-primary); }

.theme-mode__option.is-selected {
  background: var(--theme-accent-primary);
  color: var(--theme-on-accent);
}

.theme-mode__option:focus-visible {
  outline: 2px solid var(--theme-accent-primary);
  outline-offset: 2px;
}

.theme-mode__hint {
  margin: 0;
  color: var(--theme-text-muted);
  font-size: .75rem;
}
</style>

<script setup lang="ts">
type Tone = 'accent' | 'success' | 'warning' | 'danger' | 'info' | 'violet' | 'neutral'

const props = withDefaults(defineProps<{ tone?: Tone, dot?: boolean }>(), {
  tone: 'neutral',
  dot: false,
})

const TONES: Record<Tone, { fg: string, bg: string }> = {
  accent: { fg: 'var(--rv-accent)', bg: 'var(--rv-accent-soft)' },
  success: { fg: 'var(--rv-success)', bg: 'var(--rv-success-soft)' },
  warning: { fg: 'var(--rv-warning)', bg: 'var(--rv-warning-soft)' },
  danger: { fg: 'var(--rv-danger)', bg: 'var(--rv-danger-soft)' },
  info: { fg: 'var(--rv-info)', bg: 'var(--rv-info-soft)' },
  violet: { fg: 'var(--rv-violet)', bg: 'var(--rv-violet-soft)' },
  neutral: { fg: 'var(--rv-muted)', bg: 'var(--rv-surface-3)' },
}

const style = computed(() => ({ color: TONES[props.tone].fg, background: TONES[props.tone].bg }))
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-black leading-none"
    :style="style"
  >
    <span v-if="dot" class="size-1.5 rounded-full" :style="{ background: 'currentColor' }" />
    <slot />
  </span>
</template>
